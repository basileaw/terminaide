"""
ASCII art generation for Terminaide using the ansi-shadow font.

This module provides the terminascii function for generating ASCII art banners,
consolidating the original utils.py and vendor/bigfont_slim.py into a single file.
"""

from __future__ import print_function
from __future__ import division

import functools
import os
import re
import logging
import operator
import inspect
import sys
import copy
from typing import Optional

try:  # py 2/3 compatible import
    from itertools import izip as zip
except ImportError:
    pass

logger = logging.getLogger("terminaide")


# === Base Classes ===

class BaseObject(object):
    """Ancestor class for all other classes."""

    def __init__(self, *args, **kwargs):
        super(BaseObject, self).__init__()

        if args or kwargs:
            logging.debug("%s has unused parameters %s, %s"
                          % (self, args, kwargs))


# === Decorators ===

def trace(func):
    """Decorator to print arguments to called function and the return value."""

    @functools.wraps(func)
    def decorator(*args, **kwargs):
        logging.debug("%s(%s, %s)" % (func.__name__, args, kwargs))
        ret = func(*args, **kwargs)
        logging.debug("%s returned %s" % (func.__name__, ret))
        return ret

    return decorator


# === Smooshing ===

def _smoosh_spaces(left, right):
    if right == ' ':
        return left
    return right


class Smoosher(BaseObject):
    """Uses various rules to combine characters into a single character."""

    def __init__(self, **kwargs):
        super(Smoosher, self).__init__(**kwargs)
        # Only space smooshing is used in the current codebase
        self.rules = [_smoosh_spaces]

    def smoosh(self, left, right):
        """Smoosh single characters according to smooshing rules."""

        outchars = []
        for lc, rc in zip(left, right):
            for rule in self.rules:
                sc = rule(lc, rc)
                if sc is not None:
                    outchars.append(sc)
                    break

        return ''.join(outchars)


# === BigLetter ===

class BigLetter(BaseObject):
    """
    Represents a single letter in a font.
    """

    def __init__(self, lines, hardblank='$', rules=None, **kwargs):
        super(BigLetter, self).__init__(**kwargs)
        self._set_lines(lines)
        self.hardblank = hardblank
        if rules is None:
            self.rules = Smoosher(hardblank=hardblank)
        else:
            self.rules = rules

    def _set_lines(self, lines):
        self.lines = list(lines)
        self.height = len(self.lines)
        self.maxwidth = max(self.lines, key=len)

    def __str__(self):
        out = "\n".join(self.lines)
        return re.sub(re.escape(self.hardblank), ' ', out)  # remove hardblanks

    def __add__(self, other):
        """Shortcut to kern()."""
        return self.kern(other)

    def __iter__(self):
        for line in self.lines:
            yield line

    @trace
    def horizontal_space(self, other):
        """Returns the smallest amount of horizontal space between
        this letter's right side and another letter."""
        minspace = None
        for lrow, rrow in zip(self, other):
            ls = lrow.rstrip()
            rs = rrow.lstrip()
            lstripped = len(lrow) - len(ls)
            rstripped = len(rrow) - len(rs)
            separation = lstripped + rstripped
            if minspace is None or separation < minspace:
                minspace = separation
        return minspace

    def kern(self, other):
        """Overlap two letters until they touch, and return a new letter."""
        overlap = self.horizontal_space(other)
        return self.push(other, overlap=overlap)

    def push(self, other, overlap=1):
        """Push two letters together into a new one."""
        newlines = []
        for s, o in zip(self.lines, other.lines):
            if overlap < 1:
                newlines.append(s + o)
            else:
                leftchars = s[:-overlap]
                rightchars = o[overlap:]
                leftoverlap = s[-overlap:]
                rightoverlap = o[:overlap]
                overlapped = self.rules.smoosh(leftoverlap, rightoverlap)
                newlines.append(leftchars + overlapped + rightchars)
        newletter = copy.copy(self)
        newletter._set_lines(newlines)
        return newletter


# === BigFont and Font Loading ===

class BigFontError(Exception):
    pass


class BigFont(BaseObject):
    """Stores all characters from a font as a list of BigLetters."""

    def __init__(self, data=None, name=None, nonprintable=32, eol="\n", **kwargs):
        super(BigFont, self).__init__(**kwargs)
        self.nonprintable = nonprintable
        try:
            self.letters = self._extract_letters(data)
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logging.warning("load failed, %s: %s " % (exc_type, exc_value))
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

    def __getitem__(self, key):
        """Access a BigLetter from the character representation."""
        try:
            return self.letters[ord(key)]
        except IndexError:
            if self.raise_missing:
                raise KeyError("%s is not present in font" % key)
            else:
                return self.letters[ord('?')]  # fixme, return an empty Bigletter?

    def render(self, s):
        """Return string rendered in the font, suitable for printing."""
        return functools.reduce(operator.add, [self[c] for c in s])


# === Font Data (embedded ansi-shadow font) ===

ANSI_SHADOW_FONT_DATA = r"""flf2a$ 7 7 13 0 7 0 64 0
Font Author: ?

More Info:

https://web.archive.org/web/20120819044459/http://www.roysac.com/thedrawfonts-tdf.asp

FIGFont created with: http://patorjk.com/figfont-editor
$  $@
$  $@
$  $@
$  $@
$  $@
$  $@
$  $@@
██╗@
██║@
██║@
╚═╝@
██╗@
╚═╝@
   @@
@
@
@
@
@
@
@@
 ██╗ ██╗ @
████████╗@
╚██╔═██╔╝@
████████╗@
╚██╔═██╔╝@
 ╚═╝ ╚═╝ @
         @@
▄▄███▄▄·@
██╔════╝@
███████╗@
╚════██║@
███████║@
╚═▀▀▀══╝@
        @@
██╗ ██╗@
╚═╝██╔╝@
  ██╔╝ @
 ██╔╝  @
██╔╝██╗@
╚═╝ ╚═╝@
       @@
   ██╗   @
   ██║   @
████████╗@
██╔═██╔═╝@
██████║  @
╚═════╝  @
         @@
@
@
@
@
@
@
@@
 ██╗@
██╔╝@
██║ @
██║ @
╚██╗@
 ╚═╝@
    @@
██╗ @
╚██╗@
 ██║@
 ██║@
██╔╝@
╚═╝ @
    @@
      @
▄ ██╗▄@
 ████╗@
▀╚██╔▀@
  ╚═╝ @
      @
      @@
@
@
@
@
@
@
@@
   @
   @
   @
   @
▄█╗@
╚═╝@
   @@
      @
      @
█████╗@
╚════╝@
      @
      @
      @@
   @
   @
   @
   @
██╗@
╚═╝@
   @@
    ██╗@
   ██╔╝@
  ██╔╝ @
 ██╔╝  @
██╔╝   @
╚═╝    @
       @@
 ██████╗ @
██╔═████╗@
██║██╔██║@
████╔╝██║@
╚██████╔╝@
 ╚═════╝ @
         @@
 ██╗@
███║@
╚██║@
 ██║@
 ██║@
 ╚═╝@
    @@
██████╗ @
╚════██╗@
 █████╔╝@
██╔═══╝ @
███████╗@
╚══════╝@
        @@
██████╗ @
╚════██╗@
 █████╔╝@
 ╚═══██╗@
██████╔╝@
╚═════╝ @
        @@
██╗  ██╗@
██║  ██║@
███████║@
╚════██║@
     ██║@
     ╚═╝@
        @@
███████╗@
██╔════╝@
███████╗@
╚════██║@
███████║@
╚══════╝@
        @@
 ██████╗ @
██╔════╝ @
███████╗ @
██╔═══██╗@
╚██████╔╝@
 ╚═════╝ @
         @@
███████╗@
╚════██║@
    ██╔╝@
   ██╔╝ @
   ██║  @
   ╚═╝  @
        @@
 █████╗ @
██╔══██╗@
╚█████╔╝@
██╔══██╗@
╚█████╔╝@
 ╚════╝ @
        @@
 █████╗ @
██╔══██╗@
╚██████║@
 ╚═══██║@
 █████╔╝@
 ╚════╝ @
        @@
   @
██╗@
╚═╝@
██╗@
╚═╝@
   @
   @@
   @
██╗@
╚═╝@
▄█╗@
▀═╝@
   @
   @@
  ██╗@
 ██╔╝@
██╔╝ @
╚██╗ @
 ╚██╗@
  ╚═╝@
     @@
@
@
@
@
@
@
@@
██╗  @
╚██╗ @
 ╚██╗@
 ██╔╝@
██╔╝ @
╚═╝  @
     @@
██████╗ @
╚════██╗@
  ▄███╔╝@
  ▀▀══╝ @
  ██╗   @
  ╚═╝   @
        @@
 ██████╗ @
██╔═══██╗@
██║██╗██║@
██║██║██║@
╚█║████╔╝@
 ╚╝╚═══╝ @
         @@
 █████╗ @
██╔══██╗@
███████║@
██╔══██║@
██║  ██║@
╚═╝  ╚═╝@
        @@
██████╗ @
██╔══██╗@
██████╔╝@
██╔══██╗@
██████╔╝@
╚═════╝ @
        @@
 ██████╗@
██╔════╝@
██║     @
██║     @
╚██████╗@
 ╚═════╝@
        @@
██████╗ @
██╔══██╗@
██║  ██║@
██║  ██║@
██████╔╝@
╚═════╝ @
        @@
███████╗@
██╔════╝@
█████╗  @
██╔══╝  @
███████╗@
╚══════╝@
        @@
███████╗@
██╔════╝@
█████╗  @
██╔══╝  @
██║     @
╚═╝     @
        @@
 ██████╗ @
██╔════╝ @
██║  ███╗@
██║   ██║@
╚██████╔╝@
 ╚═════╝ @
         @@
██╗  ██╗@
██║  ██║@
███████║@
██╔══██║@
██║  ██║@
╚═╝  ╚═╝@
        @@
██╗@
██║@
██║@
██║@
██║@
╚═╝@
   @@
     ██╗@
     ██║@
     ██║@
██   ██║@
╚█████╔╝@
 ╚════╝ @
        @@
██╗  ██╗@
██║ ██╔╝@
█████╔╝ @
██╔═██╗ @
██║  ██╗@
╚═╝  ╚═╝@
        @@
██╗     @
██║     @
██║     @
██║     @
███████╗@
╚══════╝@
        @@
███╗   ███╗@
████╗ ████║@
██╔████╔██║@
██║╚██╔╝██║@
██║ ╚═╝ ██║@
╚═╝     ╚═╝@
           @@
███╗   ██╗@
████╗  ██║@
██╔██╗ ██║@
██║╚██╗██║@
██║ ╚████║@
╚═╝  ╚═══╝@
          @@
 ██████╗ @
██╔═══██╗@
██║   ██║@
██║   ██║@
╚██████╔╝@
 ╚═════╝ @
         @@
██████╗ @
██╔══██╗@
██████╔╝@
██╔═══╝ @
██║     @
╚═╝     @
        @@
 ██████╗ @
██╔═══██╗@
██║   ██║@
██║▄▄ ██║@
╚██████╔╝@
 ╚══▀▀═╝ @
         @@
██████╗ @
██╔══██╗@
██████╔╝@
██╔══██╗@
██║  ██║@
╚═╝  ╚═╝@
        @@
███████╗@
██╔════╝@
███████╗@
╚════██║@
███████║@
╚══════╝@
        @@
████████╗@
╚══██╔══╝@
   ██║   @
   ██║   @
   ██║   @
   ╚═╝   @
         @@
██╗   ██╗@
██║   ██║@
██║   ██║@
██║   ██║@
╚██████╔╝@
 ╚═════╝ @
         @@
██╗   ██╗@
██║   ██║@
██║   ██║@
╚██╗ ██╔╝@
 ╚████╔╝ @
  ╚═══╝  @
         @@
██╗    ██╗@
██║    ██║@
██║ █╗ ██║@
██║███╗██║@
╚███╔███╔╝@
 ╚══╝╚══╝ @
          @@
██╗  ██╗@
╚██╗██╔╝@
 ╚███╔╝ @
 ██╔██╗ @
██╔╝ ██╗@
╚═╝  ╚═╝@
        @@
██╗   ██╗@
╚██╗ ██╔╝@
 ╚████╔╝ @
  ╚██╔╝  @
   ██║   @
   ╚═╝   @
         @@
███████╗@
╚══███╔╝@
  ███╔╝ @
 ███╔╝  @
███████╗@
╚══════╝@
        @@
███╗@
██╔╝@
██║ @
██║ @
███╗@
╚══╝@
    @@
@
@
@
@
@
@
@@
███╗@
╚██║@
 ██║@
 ██║@
███║@
╚══╝@
    @@
 ███╗ @
██╔██╗@
╚═╝╚═╝@
      @
      @
      @
      @@
        @
        @
        @
        @
███████╗@
╚══════╝@
        @@
@
@
@
@
@
@
@@
 █████╗ @
██╔══██╗@
███████║@
██╔══██║@
██║  ██║@
╚═╝  ╚═╝@
        @@
██████╗ @
██╔══██╗@
██████╔╝@
██╔══██╗@
██████╔╝@
╚═════╝ @
        @@
 ██████╗@
██╔════╝@
██║     @
██║     @
╚██████╗@
 ╚═════╝@
        @@
██████╗ @
██╔══██╗@
██║  ██║@
██║  ██║@
██████╔╝@
╚═════╝ @
        @@
███████╗@
██╔════╝@
█████╗  @
██╔══╝  @
███████╗@
╚══════╝@
        @@
███████╗@
██╔════╝@
█████╗  @
██╔══╝  @
██║     @
╚═╝     @
        @@
 ██████╗ @
██╔════╝ @
██║  ███╗@
██║   ██║@
╚██████╔╝@
 ╚═════╝ @
         @@
██╗  ██╗@
██║  ██║@
███████║@
██╔══██║@
██║  ██║@
╚═╝  ╚═╝@
        @@
██╗@
██║@
██║@
██║@
██║@
╚═╝@
   @@
     ██╗@
     ██║@
     ██║@
██   ██║@
╚█████╔╝@
 ╚════╝ @
        @@
██╗  ██╗@
██║ ██╔╝@
█████╔╝ @
██╔═██╗ @
██║  ██╗@
╚═╝  ╚═╝@
        @@
██╗     @
██║     @
██║     @
██║     @
███████╗@
╚══════╝@
        @@
███╗   ███╗@
████╗ ████║@
██╔████╔██║@
██║╚██╔╝██║@
██║ ╚═╝ ██║@
╚═╝     ╚═╝@
           @@
███╗   ██╗@
████╗  ██║@
██╔██╗ ██║@
██║╚██╗██║@
██║ ╚████║@
╚═╝  ╚═══╝@
          @@
 ██████╗ @
██╔═══██╗@
██║   ██║@
██║   ██║@
╚██████╔╝@
 ╚═════╝ @
         @@
██████╗ @
██╔══██╗@
██████╔╝@
██╔═══╝ @
██║     @
╚═╝     @
        @@
 ██████╗ @
██╔═══██╗@
██║   ██║@
██║▄▄ ██║@
╚██████╔╝@
 ╚══▀▀═╝ @
         @@
██████╗ @
██╔══██╗@
██████╔╝@
██╔══██╗@
██║  ██║@
╚═╝  ╚═╝@
        @@
███████╗@
██╔════╝@
███████╗@
╚════██║@
███████║@
╚══════╝@
        @@
████████╗@
╚══██╔══╝@
   ██║   @
   ██║   @
   ██║   @
   ╚═╝   @
         @@
██╗   ██╗@
██║   ██║@
██║   ██║@
██║   ██║@
╚██████╔╝@
 ╚═════╝ @
         @@
██╗   ██╗@
██║   ██║@
██║   ██║@
╚██╗ ██╔╝@
 ╚████╔╝ @
  ╚═══╝  @
         @@
██╗    ██╗@
██║    ██║@
██║ █╗ ██║@
██║███╗██║@
╚███╔███╔╝@
 ╚══╝╚══╝ @
          @@
██╗  ██╗@
╚██╗██╔╝@
 ╚███╔╝ @
 ██╔██╗ @
██╔╝ ██╗@
╚═╝  ╚═╝@
        @@
██╗   ██╗@
╚██╗ ██╔╝@
 ╚████╔╝ @
  ╚██╔╝  @
   ██║   @
   ╚═╝   @
         @@
███████╗@
╚══███╔╝@
  ███╔╝ @
 ███╔╝  @
███████╗@
╚══════╝@
        @@
@
@
@
@
@
@
@@
@
@
@
@
@
@
@@
@
@
@
@
@
@
@@
@
@
@
@
@
@
@@
@
@
@
@
@
@
@@
@
@
@
@
@
@
@@
@
@
@
@
@
@
@@
@
@
@
@
@
@
@@
@
@
@
@
@
@
@@
@
@
@
@
@
@
@@
@
@
@
@
@
@
@@"""


# === Font Management ===

_default_font = None
_builtin_fonts = {}


def _get_builtin_font():
    """Load the built-in ansi-shadow font from embedded data."""
    global _default_font
    if _default_font is None:
        try:
            _default_font = BigFont(ANSI_SHADOW_FONT_DATA.split('\n'), name='ansi-shadow')
        except Exception:
            logging.warning("Failed to load built-in ansi-shadow font", exc_info=1)
    return _default_font


def render(text, font=None):
    """Render text in big font and return as a string.

    Uses given BigFont if specified, otherwise the built-in ansi-shadow font."""
    if font is None:
        font = _get_builtin_font()
    
    if font is None:
        return None
    
    return font.render(text)


# === Public API ===

def terminascii(text: str) -> Optional[str]:
    """
    Generate ASCII art banner from text using the ansi-shadow font.

    This function creates ASCII art text that can be used for titles,
    banners, or any decorative text display in terminal applications.

    Args:
        text: The text to convert to ASCII art

    Returns:
        ASCII art string with trailing whitespace removed, or None if generation fails

    Example:
        ```python
        from terminaide import terminascii

        banner = terminascii("HELLO")
        if banner:
            print(banner)
        ```
    """
    if not text:
        return None

    try:
        # Generate ASCII art using built-in font
        big_letter_obj = render(text)
        if big_letter_obj is None:
            logger.error("font render returned None")
            return None
        ascii_text = str(big_letter_obj)

        logger.debug(f"Generated ASCII art for text: {text}")

        # Remove ALL trailing whitespace and newlines
        ascii_text = ascii_text.rstrip()

        return ascii_text

    except Exception as e:
        logger.warning(f"Failed to generate ASCII art: {e}")
        return None