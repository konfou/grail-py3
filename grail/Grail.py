"""An extensible web browser written in pure Python."""

from grail import *

import getopt
import urllib.request
import posixpath

from tkinter import *
from io import RawIOBase

from . import filetypes
from . import tktools
from . import grailutil
from . import BaseApplication
from . import Stylesheet
from . import GlobalHistory

from .grailbase import utils
from .grailbase import GrailPrefs
from .CacheMgr import CacheManager
from .ImageCache import ImageCache
from .Authenticate import AuthenticationManager
utils._grail_root = grail_root

# Milliseconds between interrupt checks
KEEPALIVE_TIMER = 500

# Command line usage message
USAGE = """Usage: {} [options] [url]
Options:
    -i, --noimages : inhibit loading of images
    -g <geom>, --geometry <geom> : initial window geometry
    -d <display>, --display <display> : override $DISPLAY
    -q : ignore user's grailrc module""".format(sys.argv[0])


def main(args=None):
    prefs = GrailPrefs.AllPreferences()
    # XXX Disable cache for NT
    if sys.platform == 'win32':
        prefs.Set('disk-cache', 'size', '0')
    global ilu_tk
    ilu_tk = None
    if prefs.GetBoolean('security', 'enable-ilu'):
        try:
            import ilu_tk
        except ImportError:
            pass
    embedded = args is not None
    if not embedded:
        args = sys.argv[1:]
    try:
        opts, args = getopt.getopt(args, 'd:g:iq',
                                   ['display=', 'geometry=', 'noimages'])
        if len(args) > 1:
            raise getopt.error("too many arguments")
    except getopt.error as msg:
        print("Command line error:", msg, file=sys.stderr)
        print(USAGE, file=sys.stderr)
        sys.exit(2)

    geometry = prefs.Get('browser', 'initial-geometry')
    display = None
    user_init = True

    for o, a in opts:
        if o in ('-i', '--noimages'):
            load_images = False
        if o in ('-g', '--geometry'):
            geometry = a
        if o in ('-d', '--display'):
            display = a
        if o == "-q":
            user_init = False
    if args:
        url = grailutil.complete_url(args[0])
    else:
        url = None
    global app
    app = Application(prefs=prefs, display=display)
    app.embedded = embedded

    def load_images_vis_prefs(app=app):
        app.load_images = app.prefs.GetBoolean('browser', 'load-images')
    try:
        app.load_images = load_images
    except NameError:
        load_images_vis_prefs()
    prefs.AddGroupCallback('browser', load_images_vis_prefs)

    from . import SafeTkinter
    SafeTkinter._castrate(app.root.tk)

    tktools.install_keybindings(app.root)

    # Make everybody who's still using urlopen() go through the cache
    urllib.request.urlopen = app.open_url_simple

    # Add $GRAILDIR/user/ to sys.path
    subdir = os.path.join(app.graildir, 'user')
    if subdir not in sys.path:
        sys.path.insert(0, subdir)

    # Import user's grail startup file, defined as
    # $GRAILDIR/user/grailrc.py if it exists.
    if user_init:
        try:
            import grailrc
        except ImportError as e:
            # Only catch this if grailrc itself doesn't import,
            # otherwise propagate.
            if e.name != "grailrc":
                raise
        except:
            app.exception_dialog('during import of startup file')

    # Load the initial page (command line argument or from preferences)
    if not embedded:
        from .Browser import Browser
        browser = Browser(app.root, app, geometry=geometry)
        if url:
            browser.context.load(url)
        elif prefs.GetBoolean('browser', 'load-initial-page'):
            browser.home_command()

    if not embedded:
        # Give the user control
        app.go()


class URLReadWrapper(RawIOBase):

    def __init__(self, api, meta):
        self.api = api
        self.meta = meta
        self.eof = False
        RawIOBase.__init__(self)

    def info(self):
        return self.meta

    def close(self):
        api = self.api
        self.api = None
        self.meta = None
        if api:
            api.close()
        RawIOBase.close(self)

    def readable(self):
        return True

    def readinto(self, b):
        if self.eof:
            return 0
        data = self.api.getdata(len(b))
        if data:
            b[:len(data)] = data
            return len(data)
        else:
            self.eof = True
            return 0


class SocketQueue:

    def __init__(self, max_sockets):
        self.max = max_sockets
        self.blocked = []
        self.callbacks = {}
        self.open = 0

    def change_max(self, new_max):
        old_max = self.max
        self.max = new_max
        if old_max < new_max and len(self.blocked) > 0:
            for i in range(0, min(new_max - old_max, len(self.blocked))):
                # run wild free sockets
                self.open = self.open + 1
                self.callbacks.pop(self.blocked.pop(0))()

    def request_socket(self, requestor, callback):
        if self.open >= self.max:
            self.blocked.append(requestor)
            self.callbacks[requestor] = callback
        else:
            self.open = self.open + 1
            callback()

    def return_socket(self, owner):
        if owner in self.blocked:
            # died before its time
            self.blocked.remove(owner)
            del self.callbacks[owner]
        elif len(self.blocked) > 0:
            self.callbacks.pop(self.blocked.pop(0))()  # apply callback
        else:
            self.open = self.open - 1


class Application(BaseApplication.BaseApplication):

    """The application class represents a group of browser windows."""

    def __init__(self, prefs=None, display=None):
        self.root = Tk(className='Grail', screenName=display)
        self.root.withdraw()
        resources = os.path.join(script_dir, "data", "Grail.ad")
        if os.path.isfile(resources):
            self.root.option_readfile(resources, "startupFile")
        BaseApplication.BaseApplication.__init__(self, prefs)
        # The stylesheet must be initted before any Viewers, so it
        # registers its' prefs callbacks first, hence reloads before the
        # viewers reconfigure w.r.t. the new styles.
        self.stylesheet = Stylesheet.Stylesheet(self.prefs)
        self.load_images = True            # Overridden by cmd line or pref.

        # socket management
        sockets = self.prefs.GetInt('sockets', 'number')
        self.sq = SocketQueue(sockets)
        self.prefs.AddGroupCallback('sockets',
                                    lambda self=self:
                                    self.sq.change_max(
                                        self.prefs.GetInt('sockets',
                                                          'number')))

        # initialize on_exit_methods before global_history
        self.on_exit_methods = []
        self.global_history = GlobalHistory.GlobalHistory(self)
        self.login_cache = {}
        self.url_cache = CacheManager(self)
        self.image_cache = ImageCache(self.url_cache)
        self.auth = AuthenticationManager(self)
        self.root.report_callback_exception = self.report_callback_exception
        if sys.stdin.isatty():
            # only useful if stdin might generate KeyboardInterrupt
            self.keep_alive()
        self.browsers = []
        self.iostatuspanel = None
        self.in_exception_dialog = False
        from . import Greek
        for k, v in Greek.entitydefs.items():
            Application.dingbatimages[k] = (v, '_sym')
        self.root.bind_class("Text", "<Alt-Left>", self.dummy_event)
        self.root.bind_class("Text", "<Alt-Right>", self.dummy_event)

    def dummy_event(self, event):
        pass

    def register_on_exit(self, method):
        self.on_exit_methods.append(method)

    def unregister_on_exit(self, method):
        try:
            self.on_exit_methods.remove(method)
        except ValueError:
            pass

    def exit_notification(self):
        for m in self.on_exit_methods[:]:
            try:
                m()
            except:
                pass

    def add_browser(self, browser):
        self.browsers.append(browser)

    def del_browser(self, browser):
        try:
            self.browsers.remove(browser)
        except ValueError:
            pass

    def quit(self):
        self.root.quit()

    def open_io_status_panel(self):
        if not self.iostatuspanel:
            from . import IOStatusPanel
            self.iostatuspanel = IOStatusPanel.IOStatusPanel(self)
        else:
            self.iostatuspanel.reopen()

    def maybe_quit(self):
        if not (self.embedded or self.browsers):
            self.quit()

    def go(self):
        try:
            if ilu_tk:
                ilu_tk.RunMainLoop()
            else:
                self.root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self.exit_notification()

    def keep_alive(self):
        # Exercise the Python interpreter regularly so keyboard
        # interrupts get through
        self.root.tk.createtimerhandler(KEEPALIVE_TIMER, self.keep_alive)

    def get_cached_image(self, url):
        return self.image_cache.get_image(url)

    def set_cached_image(self, url, image, owner=None):
        self.image_cache.set_image(url, image, owner)

    def open_url(self, url, method, params, reload=False, data=None):
        api = self.url_cache.open(url, method, params, reload, data=data)
        api._url_ = url
        return api

    def open_url_simple(self, url):
        api = self.open_url(url, 'GET', {})
        errcode, errmsg, meta = api.getmeta()
        if errcode != 200:
            raise IOError('url open error', errcode, errmsg, meta)
        return URLReadWrapper(api, meta)

    def exception_dialog(self, message="", root=None):
        exc, val, tb = sys.exc_info()
        self.exc_dialog(message, exc, val, tb, root)

    def report_callback_exception(self, exc, val, tb, root=None):
        self.exc_dialog("in a callback function", exc, val, tb, root)

    def exc_dialog(self, message, exc, val, tb, root=None):
        if self.in_exception_dialog:
            print()
            print("*** Recursive exception", message)
            import traceback
            traceback.print_exception(exc, val, tb)
            return
        self.in_exception_dialog = True
        def f(s=self, m=message, e=exc, v=val, t=tb, root=root):
            s._exc_dialog(m, e, v, t, root)
        self.root.after_idle(f)

    def _exc_dialog(self, message, exc, val, tb, root=None):
        # XXX This needn't be a modal dialog --
        # XXX should SafeDialog be changed to support callbacks?
        from . import SafeDialog
        msg = "An exception occurred " + str(message) + " :\n"
        msg = msg + str(exc) + " : " + str(val)
        dlg = SafeDialog.Dialog(root or self.root,
                                text=msg,
                                title="Python Exception: " + str(exc),
                                bitmap='error',
                                default=0,
                                strings=("OK", "Show traceback"),
                                )
        self.in_exception_dialog = False
        if dlg.num == 1:
            self.traceback_dialog(exc, val, tb)

    def traceback_dialog(self, exc, val, tb):
        # XXX This could actually just create a new Browser window...
        from . import TbDialog
        TbDialog.TracebackDialog(self.root, exc, val, tb)

    def error_dialog(self, exc, msg, root=None):
        # Display an error dialog.
        # Return when the user clicks OK
        # XXX This needn't be a modal dialog
        from . import SafeDialog
        msg = str(msg)
        SafeDialog.Dialog(root or self.root,
                          text=msg,
                          title="Error: " + str(exc),
                          bitmap='error',
                          default=0,
                          strings=('OK',),
                          )

    dingbatimages = {'ldots': ('...', None),    # math stuff
                     'sp': (' ', None),
                     'hairsp': ('\240', None),
                     'thinsp': ('\240', None),
                     'emdash': ('--', None),
                     'endash': ('-', None),
                     'mdash': ('--', None),
                     'ndash': ('-', None),
                     'ensp': (' ', None)
                     }

    def clear_dingbat(self, entname):
        self.dingbatimages.pop(entname, None)

    def set_dingbat(self, entname, entity):
        self.dingbatimages[entname] = entity

    def load_dingbat(self, entname):
        if entname in self.dingbatimages:
            return self.dingbatimages[entname]
        gifname = grailutil.which(entname + '.gif', self.iconpath)
        if gifname:
            img = PhotoImage(file=gifname, master=self.root)
            self.dingbatimages[entname] = img
            return img
        self.dingbatimages[entname] = None
        return None
