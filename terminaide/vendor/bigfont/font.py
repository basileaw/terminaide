from __future__ import print_function
from __future__ import division

import copy
import functools
import os
import re
import logging
import operator
import pickle
import inspect
import traceback
import gzip
import sys

from zipfile import ZipFile, BadZipfile  # or BadZipFile in 3.x
from .base import BaseObject
from .letter import BigLetter
from .decorators import trace


class BigFontError(Exception):
    pass


def bigprint(text, font=None):
    """Print text in big font.

    Uses given BigFont if specified, otherwise a default font."""
    print(render(text, font))


_default_font = 'standard.flf'


def render(text, font=None):
    """Render text in big font and return as a string.

    Uses given BigFont if specified, otherwise a default font."""
    if font is None:
        if _default_font not in _builtin_fonts:
            _get_builtins()
            font = _builtin_fonts[_default_font]

    return font.render(text)


def _load_fonts(path):
    ret = {}
    for fn in os.listdir(path):
        try:
            ret[fn] = font_from_file(os.path.join(path, fn))
            root, ext = os.path.splitext(fn)
            ret[root] = ret[fn]  # also save without extension
        except Exception:
            logging.warn("import %s failed", fn, exc_info=1)
    return ret


_builtin_fonts = {}


def _get_builtins():
    """Retrieve any fonts from bigfont/fonts."""
    global _builtin_fonts
    mypath = os.path.dirname(inspect.getfile(inspect.currentframe()))
    fontpath = os.path.join(mypath, 'fonts')
    logging.info("importing all fonts from %s" % fontpath)
    _builtin_fonts = _load_fonts(fontpath)


def font_from_file(filename):
    """Extract font info from zipfile or plain text file."""
    data = None
    while 1:
        try:  # zipped?
            with ZipFile(filename, 'r') as fh:
                data = fh.read(os.path.basename(filename))
            break
        except BadZipfile as e:
            logging.info("%s does not appear to be a zipfile" % filename)

        with open(filename, 'r') as fh:
            data = fh.readlines()
        break

    try:
        return BigFont(data, name=filename)
    except BigFontError:
        raise BigFontError("file %s could not be parsed" % filename)


def font_from_pickle(fontname, pklfile='fontcache.pkl.gz'):
    with gzip.GzipFile(pklfile, 'rb') as fh:
        pklfonts = pickle.load(fh)
    return pklfonts[fontname]


def pickle_fonts(path, pklfile='fontcache.pkl.gz'):
    logging.info("importing all fonts from %s" % path)
    fonts = _load_fonts(path)
    with gzip.GzipFile(pklfile, 'wb') as fh:
        pickle.dump(fonts, fh, 2)  # protocol 2 (new, more efficient)


class BigFont(BaseObject):
    """Stores all characters from a font as a list of BigLetters."""

    def __init__(self, data=None, name=None, nonprintable=32, eol="\n", **kwargs):
        super(BigFont, self).__init__(**kwargs)
        self.nonprintable = nonprintable
        try:
            self.letters = self._extract_letters(data)
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logging.warn("load failed, %s: %s " % (exc_type, exc_value))
            raise BigFontError("font data did not make sense")
        # self.renderfcn = kern
        self.eol = eol
        self.name = name
        self.smooshrules = None  # make rules from header line
        self.raise_missing = True

    def _extract_letters(self, data):
        """Extract list of BigLetters from flf file data"""
        if data is None:
            return None
        elif isinstance(data, str):
            lines = re.split("\r?\n", data)
        else:
            lines = [line.rstrip() for line in data]

        header = self._parse_header(lines[0])
        # last char in first data line is the endchar
        endchar = lines[header['comment_lines'] + 1][-1]
        buf = []
        maxchar = 255
        letters = [None] * (maxchar + 1)
        index = 32  # first required character index
        optional_chars = re.compile(r"""^(\d+)\b.+(?<!%s)$""" % endchar)

        for line in lines:
            if index > 126:  # required chars
                m = re.match(optional_chars, line)
                if m:
                    index = int(m.group(1))
                    continue

            if index > maxchar:
                continue

            if len(line) > 1 and line[-2:] == (endchar * 2):
                buf.append(line[:-2])
                letters[index] = BigLetter(buf, hardblank=header['hardblank'])
                logging.debug("loaded character %s:\n%s" % (index, letters[index]))
                index += 1
                buf = []
            elif len(line) > 0 and line[-1] == endchar:
                buf.append(line[:-1])

        # copy required german characters to their correct positions
        # from 127-133
        moveto = (196, 214, 220, 228, 246, 252, 223)
        for idx, char in enumerate(moveto):
            if letters[char] is None and letters[idx + 127] is not None:
                letters[char] = letters[idx + 127]
                letters[idx + 127] = None

        return letters

    def __iter__(self):
        for letter in self.letters:
            if letter is not None:
                yield letter

    @trace
    def _parse_header(self, hdr):
        """Retrieve info from FIGfont header line, return as dict."""
        out = {}
        if len(hdr) < 5 or hdr[0:5] != "flf2a":
            raise BigFontError("did not understand header %s" % hdr)
        fields = hdr.split()
        out['signature'] = fields[0][0:5]
        out['hardblank'] = fields[0][5]
        out['height'] = int(fields[1])
        out['baseline'] = int(fields[2])
        out['max_length'] = int(fields[3])
        out['old_layout'] = int(fields[4])
        out['comment_lines'] = int(fields[5])
        if len(fields) > 6:
            out['print_direction'] = int(fields[6])
            out['full_layout'] = int(fields[7])
            out['codetag_count'] = int(fields[8])

        return out

    def __call__(self, s):
        """Shortcut to render()."""
        return self.render(s)

    def __getitem__(self, key):
        """Access a BigLetter from the character representation."""
        try:
            return self.letters[ord(key)]
        except IndexError as e:
            if self.raise_missing:
                raise KeyError("%s is not present in font" % key)
            else:
                return self.letters[ord('?')]  # fixme, return an empty Bigletter?

    def render(self, s):
        """Return string rendered in the font, suitable for printing."""
        return functools.reduce(operator.add, [self[c] for c in s])

    def bigprint(self, s):
        """Render and print multi-line string."""
        lines = s.split(self.eol)
        for line in lines:
            print(self.render(line))
