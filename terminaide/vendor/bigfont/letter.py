import re
import logging
import copy

try:  # py 2/3 compatible import
    from itertools import izip as zip
except ImportError:
    pass
from .smoosh import Smoosher
from .base import BaseObject
from .decorators import trace


class Rotate(BaseObject):
    clockwise = 1
    cw = 1
    counterclockwise = -1
    ccw = -1


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

    def __eq__(self, other):
        for sline, oline in zip(self, other):
            if sline != oline:
                return False
        return True

    def __iter__(self):
        for line in self.lines:
            yield line

    def touch(self, other):
        """Determine if this letter touches another letter on its right side."""
        for lr, rr in zip(self, other):
            if lr[-1] != ' ' and rr[0] != ' ':
                return True
        return False

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

    def rotate(self, rotation=Rotate.clockwise):
        if rotation == Rotate.clockwise:
            self._set_lines(''.join(reversed(chars)) for chars in zip(*self.lines))
        elif rotation == Rotate.counterclockwise:
            self._set_lines(''.join(chars) for chars in zip(*(reversed(line) for line in self.lines)))
        else:
            pass
        return self
