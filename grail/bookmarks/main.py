"""{program} -- Bookmark management utility.

usage:  {program} [options] infile [outfile]
        {program} -g|--guess-type [files...]

Options:
    -h, --help	        Display this help message.
    -g, --guess-type    Guess type of one or more bookmark files, or stdin.
    -f, --format        Specify bookmark output format ('html' or 'xbel');
                        default is 'html', except when invoked as 'bkmk2-
                        xbel', etc.
    -x                  Strip all personal information fields from output.
    --export fields     Strip specified personal fields from the output;
                        'fields' is a comma-separated list of fields.  The
                        field names are 'added', 'modified' and 'visited'.
    --scrape            Attempt to parse the input file as HTML and extract
                        links into a new bookmark file (preliminary).  The
                        input may be a URL instead of a file name.
    --search keywords   Search the input for bookmarks and folders which
                        match any of the comma-separated keywords.  Search
                        is case-insensitive.  The entire hierarchical
                        structure above the match node is returned.  If
                        there are no matches, an error is printed to stderr
                        and {program} exits with a non-zero return code.

A hyphen (-) may be used as either the input file or the output file to
indicate standard input or standard output, respectively.  If a file is
omitted, the appropriate standard stream is used.
"""


__version__ = '$Revision: 1.5 $'

from . import get_writer_class, get_format, get_parser_class, BookmarkReader
import errno
import getopt
import os
import sys


SCRIPT_PREFIX = "bkmk2"


class Options:
    guess_type = False
    output_format = "html"
    scrape_links = False
    export = False
    export_fields = []
    info = 0
    search = False
    keywords = []
    __export_field_map = {
        "modified": "last_modified",
        "visited": "last_visited",
        "added": "add_date",
        }

    def __init__(self, args):
        s, _ = os.path.splitext(os.path.basename(sys.argv[0]))
        if s.startswith(SCRIPT_PREFIX):
            s = s[len(SCRIPT_PREFIX):]
            if valid_output_format(s):
                self.output_format = s
        opts, self.args = getopt.getopt(
            sys.argv[1:], "f:ghisx",
            ["export=", "format=", "guess-type", "help", "info",
             "scrape", "search="])
        for opt, arg in opts:
            if opt in ("-h", "--help"):
                usage()
            elif opt in ("-g", "--guess-type"):
                self.guess_type = True
            elif opt in ("-f", "--format"):
                if not valid_output_format(arg):
                    usage(2, "unknown output format: " + arg)
                self.output_format = arg
            elif opt in ("-i", "--info"):
                self.info = self.info + 1
            elif opt in ("-s", "--scrape"):
                self.scrape_links = True
            elif opt == "-x":
                self.export = True
            elif opt == "--export":
                self.export = True
                fields = arg.split(",")
                print(fields)
                for f in fields:
                    fname = self.__export_field_map[f]
                    if not fname in self.export_fields:
                        self.export_fields.append(fname)
            elif opt == "--search":
                self.keywords.extend(arg.split(","))
                self.search = True


def valid_output_format(format):
    try:
        get_writer_class(format)
    except ImportError:
        return False
    else:
        return True


def main():
    try:
        options = Options(sys.argv[1:])
    except getopt.error as message:
        usage(2, message)
    args = options.args
    if options.guess_type:
        if not args:
            args = ["-"]
        for filename in args:
            guess_bookmarks_type(filename, len(args) != 1)
        return
    if len(args) > 2:
        usage(2, "too many command line arguments")
    while len(args) < 2:
        args.append('-')
    [ifn, ofn] = args
    if ifn == '-':
        infile = sys.stdin
        inbuf = infile.buffer
    else:
        try:
            infile = open(ifn, 'rb')
        except IOError as err:
            if options.scrape_links:
                # try to open as URL
                import urllib.request
                infile = urllib.request.urlopen(ifn)
                baseurl = infile.url
            else:
                error(1, "could not open {}: {}".format(ifn, err.strerror))
        else:
            baseurl = "file:" + os.path.join(os.getcwd(), ifn)
        inbuf = infile
    with infile:
        #
        # get the parser class, bypassing completely if the formats are the
        # same
        #
        if options.scrape_links:
            from .formats import html_scraper
            parser = html_scraper.Parser(ifn)
            parser.set_baseurl(baseurl)
        else:
            format = get_format(inbuf)
            if not format:
                error(1, "could not identify input file format")
            parser_class = get_parser_class(format)
            parser = parser_class(ifn)
        #
        # do the real work
        #
        writer_class = get_writer_class(options.output_format)
        root = BookmarkReader(parser).read_file(infile)
    if options.search:
        from . import search
        from .search import KeywordSearch
        search_options = KeywordSearch.KeywordOptions()
        search_options.set_keywords(" ".join(options.keywords))
        matcher = search.get_matcher("Keyword", search_options)
        root = search.find_nodes(root, matcher)
        if root is None:
            sys.stderr.write("No matches.\n")
            sys.exit(1)
    writer = writer_class(root)
    if options.export:
        from . import exporter
        export_options = exporter.ExportOptions()
        for s in options.export_fields:
            setattr(export_options, "remove_" + s, False)
        walker = exporter.ExportWalker(root, export_options)
        walker.walk()
    if options.info:
        report_info(root)
    else:
        file = None
        try:
            file = get_outfile(ofn)
            writer.write_tree(file)
        except IOError as err:
            # Ignore the error if we lost a pipe into another process.
            if err.errno != errno.EPIPE:
                raise
        finally:
            if file and ofn != "-":
                file.close()


def report_info(root):
    from . import collection
    coll = collection.Collection(root)
    total = 0
    for type, count in sorted(coll.get_type_counts().items()):
        total = total + count
        print("{:>12}: {:5}".format(type, count))
    print("{:>12}  -----".format(''))
    print("{:>12}: {:5}".format("Total", total))


def guess_bookmarks_type(filename, verbose=False):
    if filename == "-":
        type = get_format(sys.stdin.buffer)
    else:
        with open(filename, "rb") as fp:
            type = get_format(fp)
    if verbose:
        print("{}: {}".format(filename, type))
    else:
        print(type)


def get_outfile(ofn):
    if ofn == '-':
        outfile = sys.stdout.buffer
    else:
        try:
            outfile = open(ofn, 'wb')
        except IOError as err:
            error(1, "could not open {}: {}".format(ofn, err.strerror))
        print("Writing output to", ofn)
    return outfile


def usage(err=0, message=''):
    if err:
        sys.stdout = sys.stderr
    program = os.path.basename(sys.argv[0])
    if message:
        print("{}: {}".format(program, message))
        print()
    print(__doc__.format(program=program))
    sys.exit(err)


def error(err, message):
    program = os.path.basename(sys.argv[0])
    sys.stderr.write("{}: {}\n".format(program, message))
    sys.exit(err)
