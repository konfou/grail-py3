"""Parse a Grail preferences file.

The syntax is essentially a bunch of RFC822 message headers, but blank
lines and lines that don't conform to the "key: value" format are
ignored rather than aborting the parsing.  Continuation lines
(starting with whitespace) are honored properly.  Only keys of the
form group--component are retained (illegal keys are assumed to be
comments).  Group and component names (but not values) are converted
to lowercase before they are used.  Values are stripped of leading and
trailing whitespace; continuations are represented by an embedded
newline plus a space; otherwise, internal whitespace is left
unchanged.

The only argument is an open file, which will be read until EOF.

The return value is a defaultdict() of dictionaries.  The outer
dictionary represents the groups; each inner dictionary represents the
components of its group.

"""

import re
from collections import defaultdict

validpat = r'^([-_a-z0-9]*)--([-_a-z0-9]*):(.*)$'
valid = re.compile(validpat, re.IGNORECASE)

debug = False

def parseprefs(fp):
    """Parse a Grail preferences file.  See module docstring."""
    groups = defaultdict(dict)
    group = None                        # used for continuation line
    for (lineno, line) in enumerate(fp, 1):
        if line[0] == '#':
            continue
        match = None
        if line[0] in ' \t':
            # It looks line a continuation line.
            if group:
                # Continue the previous line
                value = line.strip()
                if value:
                    if group[cn]:
                        group[cn] = group[cn] + "\n " + value
                    else:
                        group[cn] = value
        else:
            match = valid.match(line)
            if match:
                # It's a header line.
                groupname, cn, value = match.group(1, 2, 3)
                groupname = groupname.lower()
                cn = cn.lower()
                value = value.strip()
                group = groups[groupname]
                group[cn] = value # XXX Override a previous value
            elif line.strip() != "":
                # It's a bad line.  Ignore it.
                if debug:
                    print("Error at", lineno, ":", repr(line))

    return groups


def test():
    """Test program for parseprefs().

    This takes a filename as command line argument;
    if no filename is given, it parses ../data/grail-defaults.
    It also times how long it takes.

    """
    import sys
    import time
    global debug
    debug = True
    if sys.argv[1:]:
        fn = sys.argv[1]
    else:
        fn = "../data/grail-defaults"
    with open(fn) as fp:
        t0 = time.time()
        groups = parseprefs(fp)
        t1 = time.time()
    print("Parsing time", round(t1-t0, 3))
    for groupname, group in sorted(groups.items()):
        print()
        print(groupname)
        print('=' * len(groupname))
        print()
        for cn, value in sorted(group.items()):
            print(cn + ":", repr(value))


if __name__ == '__main__':
    test()
