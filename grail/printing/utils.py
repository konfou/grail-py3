"""Small utility functions for printing support, mostly for debugging."""

__version__ = '$Revision: 1.6 $'

import os
import sys


def find_word_breaks(data):
    datalen = nextbrk = len(data)
    prevbreaks = [-1] * datalen
    nextbreaks = [datalen] * datalen
    indexes = range(datalen)
    #
    prevbrk = -1
    for i in indexes:
        prevbreaks[i] = prevbrk
        if data[i] == ' ':
            prevbrk = i
    #
    for i in reversed(indexes):
        nextbreaks[i] = nextbrk
        if data[i] == ' ':
            nextbrk = i
    #
    return prevbreaks, nextbreaks


_subsystems = {}

def debug(text, subsystem=None):
    if get_debugging(subsystem):
        if text[-1] != '\n':
            text = text + '\n'
        sys.stderr.write(text)
        sys.stderr.flush()


def set_debugging(flag, subsystem=None):
    _subsystems.setdefault(subsystem, 0)
    _subsystems[subsystem] = max(
        _subsystems[subsystem] + (1 if flag else -1), 0)


def get_debugging(subsystem=None):
    if subsystem in _subsystems:
        return _subsystems[subsystem]
    if subsystem:
        return get_debugging()
    return 0


# unit conversions:
def inch_to_pt(inches): return inches * 72.0
def pt_to_inch(points): return points / 72.0


def distance(start, end):
    """Returns the distance between two points."""
    if start < 0 and end < 0:
        return abs(min(start, end) - max(start, end))
    elif start >= 0 and end >= 0:
        return max(start, end) - min(start, end)
    else:
        #  one neg, one pos
        return max(start, end) - min(start, end)


def image_loader(url):
    """Simple image loader for the PrintingHTMLParser instance."""
    #
    # This needs a lot of work for efficiency and connectivity
    # with the rest of Grail, but works O.K. if there aren't many images
    # or if blocking can be tolerated.
    #
    # Some sites don't handle this very well, including www.microsoft.com,
    # which returns HTTP 406 errors when html2ps is used as a script
    # (406 = "No acceptable objects were found").
    #
    from urllib.request import urlopen
    try:
        imgfp = urlopen(url)
    except IOError:
        return None
    with imgfp:
        return imgfp.read()


def which(filename, path=()):
    for p in path:
        fn = os.path.join(p, filename)
        if os.path.exists(fn):
            return fn
    return None


def conv_fontsize(spec):
    """Parse a font size with an optional leading specification.

    spec
        should be a string representing a real number or a pair of real
        numbers separated by a forward slash.  Whitespace is ignored.

    This function returns a tuple of the fontsize and leading.  If the
    leading is not specified by `spec', the leading will be the same as
    the font size.

    """
    if '/' in spec:
        spec = spec.split('/')
        if len(spec) != 2:
            raise ValueError("illegal font size specification")
    else:
        spec = [spec, spec]
    return map(float, spec)
