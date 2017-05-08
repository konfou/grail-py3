"""FTP interface using the new protocol API.

XXX Main deficiencies:

- poll*() always returns ready
- should read the headers more carefully (no blocking)
- (could even *write* the headers more carefully)
- should poll the connection making part too
- no GC of ftp cache entries
- should reuse ftp cache entries for same server by using cdup/cd
- if a file retrieval returns error 550 it is retried as directory listing

"""


import re

import ftplib
from urllib.parse import unquote, splithost, splitport, splituser, \
     splitpasswd, splitattr, splitvalue, quote
from urllib.parse import urljoin
from .. import grailutil
import socket
import html
from xml.sax import saxutils

app = grailutil.get_grailapp()          # app.guess_type(url)


# Stages
META = 'META'
DATA = 'DATA'
EOF = 'EOF'
DONE = 'DONE'


LISTING_HEADER = """<HTML>
<HEAD><TITLE>FTP Directory: {url}</TITLE></HEAD>
<BODY>
<H1>FTP Directory: {url}</H1>
<PRE>"""

LISTING_TRAILER = """</PRE>
</BODY>
"""

# pattern catches file names with embedded spaces and correctly chops
# off symbolic links.  assumption is anything after `yyyy' or `hh:mm'
# field and before optional `-> symlink' field is the name of the file
LISTING_PATTERN = r"""
    ^(                               # group 1
        [-a-z]                        # file type
        [-a-z][-a-z][-a-z]            # owner rwx
        [-a-z][-a-z][-a-z]            # group rwx
        [-a-z][-a-z][-a-z]            # world rwx
    )                                # end group 1
    (                                # group 2
        [ \t]+.*[ \t]+                # links, owner, grp, sz, mnth, day
        [0-9][0-9]:?[0-9][0-9]        # year or hh:mm
        [ \t]+                        # spaces
    )                                # end group 2
    (                                # group 3
        ([^-]|-[^>])+              # lots of chars, but not symlink
    )                                # end group 3
    (                                # optional group 5
        [ \t]+->.*                    # spaces followed by symlink 
    )?                               # end optional group 5
    $                                 # end of string
    """


ftpcache = {}                           # XXX Ouch!  A global!


class ftp_access:

    def __init__(self, url, method, params):
        assert method == 'GET'
        netloc, path = splithost(url)
        if not netloc: raise IOError('ftp error', 'no host given')
        host, port = splitport(netloc)
        user, host = splituser(host)
        if user: user, passwd = splitpasswd(user)
        else: passwd = None
        host = socket.gethostbyname(host)
        if port:
            try:
                port = int(port)
            except ValueError:
                raise IOError('ftp error', 'bad port')
        else:
            port = ftplib.FTP_PORT
        path, attrs = splitattr(path)
        self.url = "ftp://{}{}".format(netloc, path)
        dirs = path.split('/')
        dirs, file = dirs[:-1], dirs[-1]
        self.content_length = None
        if not file:
            self.content_type, self.content_encoding = None, None
            type = 'd'
        else:
            self.content_type, self.content_encoding = app.guess_type(file)
            if self.content_encoding:
                type = 'i'
            elif self.content_type and self.content_type.startswith('text/'):
                type = 'a'
            elif file[-1] == '/':
                type = 'd'
            else:
                type = 'i'
        if dirs and not dirs[0]: dirs = dirs[1:]
        key = (user, host, port, '/'.join(dirs))
        self.debuglevel = 0
        try:
            ftpcache.setdefault(key, [])
            for attr in attrs:
                [attr, value] = map(str.lower, splitvalue(attr))
                if attr == 'type' and value in ('a', 'i', 'd'):
                    type = value
                elif attr == 'debug':
                    try:
                        self.debuglevel = int(value)
                    except ValueError:
                        pass
            candidates = ftpcache[key]
            for cand in candidates:
                if not cand.busy():
                    break
            else:
                cand = ftpwrapper(user, passwd,
                                  host, port, dirs, self.debuglevel)
                candidates.append(cand)
            # XXX Ought to clean the cache every once in a while
            self.cand = cand
            self.sock, self.isdir = cand.retrfile(file, type)
            self.content_length = cand.content_length
        except ftplib.all_errors as msg:
            raise IOError('ftp error', msg)
        self.state = META

    def pollmeta(self):
        assert self.state == META
        return "Ready", True

    def getmeta(self):
        assert self.state == META
        self.state = DATA
        headers = {}
        if self.isdir:
            if self.url and not self.url.endswith('/'):
                self.url = self.url + '/'
            self.content_type = 'text/html'
            self.content_encoding = None
        if self.content_type:
            headers['content-type'] = self.content_type
        if self.content_encoding:
            headers['content-encoding'] = self.content_encoding
        if self.content_length:
            headers['content-length'] = format(self.content_length)
        self.lines = []                 # Only used if self.isdir
        return 200, "OK", headers

    def polldata(self):
        assert self.state in (EOF, DATA)
        return "Ready", True

    def getdata(self, maxbytes):
        if self.state == EOF:
            self.state = DONE
            return b""
        assert self.state == DATA
        data = self.sock.recv(maxbytes)
        if self.debuglevel > 4: print("*data*", repr(data))
        if not data:
            self.state = DONE
        if self.isdir:
            self.addlistingdata(data)
            data = self.getlistingdata()
            if self.state == DONE and data:
                self.state = EOF        # Allow one more call
        return data

    def addlistingdata(self, data):
        if not data:
            if self.lines:
                while self.lines and self.lines[-1] == "":
                    del self.lines[-1]
                self.lines.append(None) # Mark the end
        else:
            lines = data.decode('latin-1').split('\n')
            if self.debuglevel > 3:
                for line in lines: print("*addl*", repr(line))
            if self.lines:
                lines[0] = self.lines[-1] + lines[0]
                self.lines[-1:] = lines
            else:
                lines.insert(0, None)   # Mark the start
                self.lines = lines

    def getlistingdata(self):
        if not self.lines:
            return b""
        lines, self.lines = self.lines[:-1], self.lines[-1:]
        data = ""
        prog = re.compile(self.listing_pattern, re.VERBOSE)
        for line in lines:
            if self.debuglevel > 2:
                print("*getl*", repr(line))
            if line is None:
                data = data + self.listing_header.format(url=
                                                     html.escape(self.url))
                continue
            if line[-1:] == '\r': line = line[:-1]
            m = prog.match(line) 
            if not m:
                line = saxutils.escape(line) + '\n'
                data = data + line
                continue
            mode, middle, name, symlink = m.group(1, 2, 3, 5)
            rawname = name
            [mode, middle, name] = map(saxutils.escape, [mode, middle, name])
            href = urljoin(self.url, quote(rawname))
            if len(mode) == 10 and mode[0] == 'd' or name.endswith('/'):
                if not name.endswith('/'):
                    name = name + '/'
                if not href.endswith('/'):
                    href = href + '/'
            line = '{}{}<A HREF={}>{}</A>{}\n'.format(
                mode, middle, saxutils.quoteattr(href), name,
                (symlink or ''))
            data = data + line
        if self.lines == [None]:
            data = data + self.listing_trailer
            self.lines = []
        return data.encode('latin-1', 'xmlcharrefreplace')

    listing_header = LISTING_HEADER
    listing_trailer = LISTING_TRAILER
    listing_pattern = LISTING_PATTERN

    def fileno(self):
        return self.sock.fileno()

    def close(self):
        sock = self.sock
        cand = self.cand
        self.sock = None
        self.cand = None
        if sock:
            sock.close()
        if cand:
            cand.done()


class ftpwrapper:

    """Helper class for cache of open FTP connections"""

    def __init__(self, user, passwd, host, port, dirs, debuglevel=None):
        self.user = unquote(user or '')
        self.passwd = unquote(passwd or '')
        self.host = host
        self.port = port
        self.dirs = []
        self.content_length = None
        for dir in dirs:
            self.dirs.append(unquote(dir))
        self.debuglevel = debuglevel
        self.reset()

    def __del__(self):
        self.done()
        self.ftp.quit()

    def reset(self):
        self.conn = None
        self.ftp = ftplib.FTP()
        if self.debuglevel is not None:
            self.ftp.set_debuglevel(self.debuglevel)
        self.ftp.connect(self.host, self.port)
        self.ftp.login(self.user, self.passwd)
        for dir in self.dirs:
            self.ftp.cwd(dir)

    def busy(self):
        return bool(self.conn)

    def done(self):
        conn = self.conn
        self.conn = None
        if conn:
            conn.close()
            try:
                self.ftp.voidresp()
            except ftplib.all_errors:
                print("[ftp.voidresp() failed]")

    def retrfile(self, file, type):
        isdir = type == 'd'
        if isdir: cmd = 'TYPE A'
        else: cmd = 'TYPE ' + type.upper()
        try:
            self.ftp.voidcmd(cmd)
        except ftplib.all_errors:
            self.reset()
            self.ftp.voidcmd(cmd)
        conn = None
        if file and not isdir:
            try:
                cmd = 'RETR ' + unquote(file)
                conn, self.content_length = self.ftp.ntransfercmd(cmd)
            except ftplib.error_perm as reason:
                if not str(reason).startswith('550'):
                    raise IOError('ftp error', reason)
        if not conn:
            # Try a directory listing
            isdir = True
            if file: cmd = 'LIST ' + file
            else: cmd = 'LIST'
            conn = self.ftp.transfercmd(cmd)
        self.conn = conn
        return conn, isdir


# To test this, use ProtocolAPI.test()
