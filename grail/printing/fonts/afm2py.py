#! /usr/bin/env python

"""Adobe Font Metric conversion script.

This script extracts character width font metrics from Adobe Font
Metric (AFM) files.  Output is suitable for use with Grail's
PostScript printing tools.

Usage: {program} [-h] [-d <dir>] <afmfile>

    -h
    --help      -- print this help message

    -d
    --dir <dir> -- directory to write the output file in

    <afmfile>   -- the filename of the file to convert.

Output goes to a file created from the name of the font.  E.g. if the
FontName of the font is Courier-Bold, the output file is named
PSFont_Courier_Bold.py.

"""

import sys
import os
import getopt



program = sys.argv[0]

def usage(status):
    print(__doc__.format_map(globals()))
    sys.exit(status)


def splitline(line):
    keyword, _, rest = line.partition(' ')
    rest = rest.strip()
    return keyword.lower(), rest



# Mappings between character names and their ordinal equivalents.

def read_unicode_mapping(filename, dict=None):
    result = dict or {}
    with open(filename) as fp:
        for line in fp:
            line = line.strip()
            if line and line[0] == "#":
                continue
            parts = line.split("#")
            if len(parts) != 3:
                continue
            parts[0:1] = parts[0].split()
            if len(parts) != 4:
                continue
            unicode = int(parts[0], 16)
            adobe_name = parts[3].strip()
            if unicode < 256:
                result.setdefault(adobe_name, unicode)
    return result

LATIN_1_MAPPING = {
    'copyright': 169,
    }

# TBD: when we support other character sets, we should generalize
# this.  No need to do so now though.
charset = LATIN_1_MAPPING



TEMPLATE = """\
# Character width information for PostScript font `{fullname}'
# generated from the Adobe Font Metric file `{filename}'.  Adobe
# copyright notice follows:
#
# {notice}
#
from . import PSFont
font = PSFont.PSFont('{fontname}', '{fullname}',
"""

FORMAT = ', '.join(['{:4}'] * 8) + ','


def parse(filename, outdir):
    cwidths = [0] * 256
    tdict = {'fontname': '',
             'fullname': '',
             'filename': filename,
             'notice':   '',
             }

    with open(filename, 'r') as infp:
        for line in infp:
            keyword, rest = splitline(line)
            if keyword in ('fontname', 'fullname', 'notice'):
                tdict[keyword] = rest
            if keyword == 'startcharmetrics':
                break
        else:
            print('No character metrics found in file:', filename)
            sys.exit(1)

        outfile = os.path.join(
            outdir,
            '_'.join(['PSFont'] + tdict['fontname'].split('-')) + '.py')

        # read the character metrics into the list
        for line in infp:
            keyword, rest = splitline(line)
            if keyword == 'c':
                info = rest.split()
                charnum = int(info[0])
                charname = info[6]
                width = int(info[3])
                if charname in charset:
                    cwidths[charset[charname]] = width
                elif 0 <= charnum < 256:
                    cwidths[charnum] = width

            if keyword == 'endcharmetrics':
                break

    with open(outfile, 'w') as outfp:
        outfp.write(TEMPLATE.format_map(tdict))
        outfp.write('[ ')
        for i in range(0, 256, 8):
            if i != 0:
                outfp.write('  ')
            print(FORMAT.format(*cwidths[i:i+8]), file=outfp)
        print('])', file=outfp)



def main():
    help = False
    status = 0

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hd:m:',
                                   ['dir', 'help', 'map'])
    except getopt.error as msg:
        print(msg)
        usage(1)

    if len(args) != 1:
        usage(1)

    filename = args[0]
    outdir = '.'
    mapfile = None
    for opt, arg in opts:
        if opt in ('-h', '--help'):
            help = True
        elif opt in ('-d', '--dir'):
            outdir = arg
        elif opt in ('-m', '--map'):
            mapfile = arg

    if help:
        usage(status)

    if mapfile:
        read_unicode_mapping(mapfile, LATIN_1_MAPPING)

    parse(filename, outdir)


if __name__ == '__main__':
    main()
