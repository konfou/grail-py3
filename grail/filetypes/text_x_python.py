"""<OBJECT> handler for Python applets."""

__version__ = '$Revision: 1.5 $'

from .. import grailutil
import re
import tkinter
import token

from .. import AppletLoader
from ..sgml import HTMLParser

whitespace = '\\t\\n\x0b\x0c\\r '


def embed_text_x_python(parser, attrs):
    """<OBJECT> Handler for Python applets."""
    extract = grailutil.extract_keyword
    width = extract('width', attrs, conv=int)
    height = extract('height', attrs, conv=int)
    menu = extract('menu', attrs, conv=str.strip)
    classid = extract('classid', attrs, conv=str.strip)
    codebase = extract('codebase', attrs, conv=str.strip)
    align = extract('align', attrs, 'baseline')
    vspace = extract('vspace', attrs, 0, conv=int)
    hspace = extract('hspace', attrs, 0, conv=int)
    apploader = AppletLoader.AppletLoader(
        parser, width=width, height=height, menu=menu,
        classid=classid, codebase=codebase,
        vspace=vspace, hspace=hspace, align=align, reload=parser.reload1)
    if apploader.feasible():
        return AppletEmbedding(apploader)
    else:
        apploader.close()
        return None


class AppletEmbedding(HTMLParser.Embedding):
    """Applet interface for use with <OBJECT> / <PARAM> elements."""

    def __init__(self, apploader):
        self.__apploader = apploader

    def param(self, name, value):
        self.__apploader.set_param(name, value)

    def end(self):
        self.__apploader.go_for_it()

ws_width = re.compile("[{}]*".format(whitespace)).match


class parse_text_x_python:
    def __init__(self, viewer, reload=False):
        self.__viewer = viewer
        self.__source = ''
        viewer.new_font((None, False, False, True))

    def feed(self, data):
        self.__source = self.__source + data
        self.__viewer.send_literal_data(data)

    IGNORED_TERMINALS = (
        token.ENDMARKER, token.NEWLINE, token.INDENT, token.DEDENT)
    __wanted_terminals = set()
    for ntype in token.tok_name.keys():
        if token.ISTERMINAL(ntype) and ntype not in IGNORED_TERMINALS:
            __wanted_terminals.add(ntype)

    def close(self):
        self.show("Colorizing Python source text - parsing...")
        import parser
        try:
            nodes = parser.st2list(parser.suite(self.__source), True)
        except parser.ParserError as err:
            self.__viewer.context.message(
                "Syntax error in Python source: {}".format(err))
            return
        self.setup_tags()
        ISTERMINAL = token.ISTERMINAL
        wanted = self.__wanted_terminals.__contains__
        tag_add = self.tag_add = self.__viewer.text.tag_add
        colorize = self.colorize
        prevline, prevcol = 0, 0
        sourcetext = self.__source.split("\n")
        sourcetext.insert(0, '')
        self.show("Colorizing Python source text - coloring...")
        steps = 0
        while nodes:
            steps = steps + 1
            if not (steps % 2000): self.show()
            node = nodes.pop(0)
            if isinstance(node, list):
                ntype = node[0]
                if wanted(ntype):
                   [ntype, nstr, lineno] = node
                   # The parser spits out the line number the token ENDS on,
                   # not the line it starts on!
                   if ntype == token.STRING and "\n" in nstr:
                       strlines = nstr.split("\n")
                       endpos = lineno, len(strlines[-1]), sourcetext[lineno]
                       lineno = lineno - len(strlines) + 1
                   else:
                       endpos = ()
                   if prevline != lineno:
                       start = "{}.{}".format(prevline, prevcol)
                       end = "{}.0".format(lineno)
                       tag_add('python:comment', start, end)
                       prevcol = 0
                       prevline = lineno
                       sourceline = sourcetext[lineno]
                   match = ws_width(sourceline, prevcol)
                   if match:
                       prevcol = match.end()
                   colorize(ntype, nstr, lineno, prevcol)
                   # point prevline/prevcol to 1st char after token:
                   if endpos:
                       prevline, prevcol, sourceline = endpos
                   else:
                       prevcol = prevcol + len(nstr)
                else:
                    nodes = node[1:] + nodes
        # end of last token to EOF is a comment...
        start = "{}.{}".format(prevline or 1, prevcol)
        tag_add('python:comment', start, tkinter.END)
        self.__viewer.context.message_clear()
        self.tag_add = None

    def show(self, message=None):
        if message:
            self.__viewer.context.message(message)
        self.__viewer.context.browser.root.update_idletasks()

    # Each element in this table maps an identifier to a tuple of
    # the tag it should be marked with and the tag the next token
    # should be marked with (or None).
    #
    __keywords = {
        'False': ('python:special', None),
        'None': ('python:special', None),
        'True': ('python:special', None),
        'and': ('python:operator', None),
        'as': ('python:statement', None),
        'assert': ('python:statement', None),
        'break': ('python:control', None),
        'class': ('python:define', 'python:class'),
        'continue': ('python:control', None),
        'def': ('python:define', 'python:def'),
        'del': ('python:statement', None),
        'elif': ('python:control', None),
        'else': ('python:control', None),
        'except': ('python:control', None),
        'finally': ('python:control', None),
        'for': ('python:control', None),
        'from': ('python:statement', None),
        'global': ('python:statement', None),
        'if': ('python:control', None),
        'import': ('python:statement', None),
        'in': ('python:operator', None),
        'is': ('python:operator', None),
        'lambda': ('python:operator', None),
        'nonlocal': ('python:statement', None),
        'not': ('python:operator', None),
        'or': ('python:operator', None),
        'pass': ('python:statement', None),
        'raise': ('python:control', None),
        'return': ('python:control', None),
        'try': ('python:control', None),
        'while': ('python:control', None),
        'with': ('python:control', None),
        'yield': ('python:control', None),
        }
    import types
    for name in dir(types):
        if name.endswith("Type"):
            __keywords[name] = ('python:special', None)

    __next_tag = None
    def colorize(self, ntype, nstr, lineno, colno):
        """Colorize a single token.

        ntype
            Node type.  This is guaranteed to be a terminal token type
            not listed in self.IGNORE_TERMINALS.

        nstr
            String containing the token, uninterpreted.

        lineno
            Line number (1-based) of the line on which the token starts.

        colno
            Index into the source line at which the token starts. <TAB>s
            are not counted specially.

        """
        start = "{}.{}".format(lineno, colno)
        end = "{} + {} chars".format(start, len(nstr))
        if self.__next_tag:
            self.tag_add(self.__next_tag, start, end)
            self.__next_tag = None
        elif nstr in self.__keywords:
            tag, self.__next_tag = self.__keywords[nstr]
            self.tag_add(tag, start, end)
        elif ntype == token.STRING:
            qw = 1			# number of leading/trailing quotation
            if nstr[0] == nstr[1]:	# marks -- `quote width'
                qw = 3
            start = "{}.{}".format(lineno, colno + qw)
            end = "{} + {} chars".format(start, len(nstr) - (2 * qw))
            self.tag_add("python:string", start, end)

    # Set foreground colors from this tag==>color table:
    __foregrounds = {
        'python:class': 'darkGreen',
        'python:comment': 'mediumBlue',
        'python:control': 'midnightBlue',
        'python:def': 'saddleBrown',
        'python:define': 'midnightBlue',
        'python:operator': 'midnightBlue',
        'python:special': 'darkGreen',
        'python:statement': 'midnightBlue',
        'python:string': 'steelblue4',
        }

    def setup_tags(self):
        """Configure the display tags associated with Python source coloring.

        This is called only if the source is correctly parsed.  All mapping
        of logical tags to physical style is accomplished in this method.

        """
        self.__viewer.configure_fonttag('_tt_b')
        self.__viewer.configure_fonttag('_tt_i')
        text = self.__viewer.text
        boldfont = text.tag_cget('_tt_b', '-font')
        italicfont = text.tag_cget('_tt_i', '-font')
        text.tag_config('python:string', font=italicfont)
        for tag in ('python:class', 'python:def', 'python:define'):
            text.tag_config(tag, font=boldfont)
        for tag, color in self.__foregrounds.items():
            text.tag_config(tag, foreground=color)
