import logging

try:  # py 2/3 compatible import
    from itertools import izip as zip
except ImportError:
    pass
from .base import BaseObject


def _smoosh_spaces(left, right):
    if right == ' ':
        return left
    return right


def _smoosh_universal(left, right):
    return right


def _smoosh_equal(left, right, hardblank='$'):
    if left == right and left != hardblank:
        return left
    return None


def _smoosh_underscore(left, right):
    replacers = r"""|/\[]{}()<>"""
    if right == "_" and left in replacers:
        return left
    if left == "_" and right in replacers:
        return right
    return None


def _smoosh_hierarchy(left, right):
    replacers = {"|": 1,
                 "/": 2, "\\": 2,
                 "[": 3, "]": 3,
                 "{": 4, "}": 4,
                 "(": 5, ")": 5,
                 "<": 6, ">": 6}
    try:
        rleft = replacers[left]
        rright = replacers[right]
    except KeyError:
        return None

    if rleft > rright:
        return left
    if rright > rleft:
        return right
    return None


def _smoosh_opposite(left, right):
    pairs = ("[]", "][", "{}", "}{", "()", ")(")
    if left + right in pairs:
        return "|"
    return None


def _smoosh_bigx(left, right):
    both = left + right
    if both == "/\\":
        return "|"
    if both == "\\/":
        return "Y"
    if both == "><":
        return "X"
    return None


def _smoosh_hardblank(left, right, hardblank='$'):
    if left == right and left == hardblank:
        return left
    return None


def _smoosh_horizontal_line(top, bot):
    both = top + bot
    if both == "-_" or both == "_-":
        return "="
    return None


class Smoosher(BaseObject):
    """Uses various rules to combine characters into a single character."""

    def __init__(self,
                 universal=False,
                 equal_char=False,
                 underscore=False,
                 hierarchy=False,
                 opposite_pair=False,
                 big_x=False,
                 hardblank=False,
                 vertical_equal_char=False,
                 vertical_underscore=False,
                 vertical_hierarchy=False,
                 horizontal_line=False,
                 vertical_line=False,
                 unknown_char='?',
                 **kwargs):
        super(Smoosher, self).__init__(**kwargs)
        self.universal = universal
        self.equal_char = equal_char
        self.underscore = underscore
        self.hierarchy = hierarchy
        self.opposite_pair = opposite_pair
        self.big_x = big_x
        self.hardblank = hardblank
        self.vertical_equal_char = equal_char
        self.vertical_underscore = underscore
        self.vertical_hierarchy = hierarchy
        self.horizontal_line = horizontal_line
        self.vertical_line = vertical_line
        self.unknown_char = unknown_char

        # fixme, make sure rules passed from header and populate here
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
