"""Simple 'Document Info...' dialog for Grail."""

__version__ = '$Revision: 2.16 $'

import re
import tkinter
from . import tktools
import urllib.parse
from . import CacheMgr

FIELD_BREAKER = str.maketrans("&", "\n")
MAX_TEXT_FIELD_LINES = 10


class DocumentInfoDialog:
    def __init__(self, master, context, class_="DocumentInfo"):
        root = tktools.make_toplevel(master, class_=class_,
                                     title="Document Info")
        self.root = root
        self.app = context.app
        page_title = context.page.title()
        if page_title:
            root.title("Document Info: " + page_title)
        destroy = self.destroy
        for seq in ("<Alt-W>", "<Alt-w>", "<Return>"):
            root.bind(destroy)
        root.protocol("WM_DELETE_WINDOW", destroy)
        frame, self.__topfr, botfr = tktools.make_double_frame(root)
        #
        # Info display
        #
        url = context.page.url()
        scheme, netloc, path, params, query, fragment = \
            urllib.parse.urlparse(url)
        url = urllib.parse.urlunparse((scheme, netloc, path, '', '', ''))
        self.add_label_field("Title", page_title or "(unknown)", "title")
        self.add_label_field("URI", url, "uri")
        if fragment:
            self.add_label_field("Fragment", fragment, "fragment")
        headers = context.get_headers()
        if isinstance(headers.get("date"), CacheMgr.HTTime):
            self.add_label_field("", "(Loaded from local cache.)", "cached")
        s = ""
        for k, v in sorted(headers.items()):
            if k == 'date' and isinstance(v, CacheMgr.HTTime):
                from . import ht_time
                v = ht_time.unparse(v.get_secs())
            s = "{}{}:\t{}\n".format(s, k, v)
        stretch = self.add_text_field("Response headers", s, "headers")
        if query:
            query = query.translate(FIELD_BREAKER)
            stretch = stretch or \
                      self.add_text_field("Query fields", query, "query")
        postdata = context.get_postdata()
        if postdata:
            postdata = postdata.decode().translate(FIELD_BREAKER)
            stretch = stretch or \
                      self.add_text_field("POST fields", postdata, "postdata")
        #
        # Bottom button
        #
        fr = tkinter.Frame(botfr, borderwidth=1, relief=tkinter.SUNKEN)
        fr.pack()
        btn = tkinter.Button(fr, text="OK", command=destroy)
        # '2m' is the value from the standard Tk 'tk_dialog' command
        btn.pack(padx='2m', pady='2m')
        btn.focus_set()
        #
        del self.__topfr                # lose the reference
        tktools.set_transient(root, master)
        root.update_idletasks()
        reqwidth = root.winfo_reqwidth()
        reqheight = root.winfo_reqheight()
        root.minsize(reqwidth, reqheight)
        if not stretch:
            root.maxsize(reqwidth, reqheight)

    def destroy(self, event=None):
        self.root.destroy()

    def add_field(self, label, name):
        fr = tkinter.Frame(self.__topfr, name=name, class_="Dataitem")
        fr.pack(fill=tkinter.X)
        if label: label = label + ": "
        tkinter.Label(fr, text=label, width=17, anchor=tkinter.E, name="label"
                      ).pack(anchor=tkinter.NE, side=tkinter.LEFT)
        return fr

    __boldpat = re.compile(r'-([a-z]*bold|demi)-', re.IGNORECASE)
    __datafont = None
    def add_label_field(self, label, value, name):
        fr = self.add_field(label, name)
        label = tkinter.Label(fr, text=value, anchor=tkinter.W, name="value")
        datafont = self.__datafont
        if datafont is None:
            # try to get a medium-weight version of the font if bold:
            font = label['font']
            match = self.__boldpat.search(font)
            if match:
                pos = match.start() + 1
                end = match.end()
                datafont = "{}medium{}".format(font[:pos], font[end:])
                DocumentInfoDialog.__datafont = datafont
            else:
                # don't try again:
                DocumentInfoDialog.__datafont = ''
        if datafont:
            try: label['font'] = datafont
            except TclError: DocumentInfoDialog.__datafont = ''
        label.pack(anchor=tkinter.W, fill=tkinter.X, expand=1)
        return label

    def add_text_field(self, label, value, name):
        """Add a text field; return true if it can be stretched vertically."""
        fr = self.add_field(label, name)
        if value and value[-1] != "\n":
            value = value + "\n"
        maxlines = 1 + value.count("\n")
        text, frame = tktools.make_text_box(
            fr, takefocus=0, width=60, vbar=1,
            height=min(MAX_TEXT_FIELD_LINES, maxlines))
        frame.pack(side=tkinter.LEFT, expand=1, fill=tkinter.BOTH)
        fr.pack(expand=1, fill=tkinter.BOTH)
        text.insert(tkinter.END, value)
        text["state"] = tkinter.DISABLED
        return maxlines > MAX_TEXT_FIELD_LINES


class DocumentInfoCommand:
    def __init__(self, obj):
        self.__viewer = getattr(obj, "viewer", obj)

    def __call__(self, event=None):
        DocumentInfoDialog(self.__viewer.master,
                           self.__viewer.context)
