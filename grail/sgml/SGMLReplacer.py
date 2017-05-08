"""Simple parser that handles only what's allowed in attribute values."""
__version__ = '$Revision: 1.12 $'

import re
import string
from .SGMLLexer import *


_entref_exp = re.compile(r'&((#|)[a-zA-Z0-9][-.a-zA-Z0-9]*)(;|)')

_named_chars = {'#re' : '\r',
                '#rs' : '\n',
                '#space' : ' '}

for i in range(256):
    _named_chars["#{}".format(i)] = chr(i)

_chartable = str.maketrans(string.whitespace, " " * len(string.whitespace))


def replace(data, entities = None):
    """Perform general entity replacement on a string.
    """
    data = data.translate(_chartable)
    if '&' in data and entities:
        match = _entref_exp.search(data)
        if match:
            pos = match.start()
        else:
            pos = -1
        while pos >= 0 and pos + 1 < len(data):
            pos = match.start()
            ref, term = match.group(1, 3)
            if ref in entities:
                value = entities[ref]
            else:
                value = _named_chars.get(ref.lower())
            if value is not None:
                data = data[:pos] + value + data[pos+len(ref)+len(term)+1:]
                pos = pos + len(value)
            else:
                pos = pos + len(ref) + len(term) + 1
            match = _entref_exp.search(data)
            if match:
                pos = match.start()
            else:
                pos = -1
    return data
