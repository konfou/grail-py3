"""Footnote support for Grail.

This supports the <FN ID=name> form of the footnote tag.
"""

__version__ = '$Revision: 2.9 $'


def writer_start_fn(parser, attrs):
    if 'p' in parser.stack:
        parser.lex_endtag('p')
        parser.formatter.end_paragraph(0)
    else:
        parser.formatter.add_line_break()


def writer_end_fn(parser):
    parser.formatter.pop_style()
