import unittest
import os
import copy
import inspect
from . import font
from .letter import BigLetter, Rotate
from .font import font_from_file

FONT_DIR = os.path.join(os.path.dirname(inspect.getfile(inspect.currentframe())), 'fonts')


class BasicBigLetterTests(unittest.TestCase):
    def setUp(self):
        d = ["|-\\", "| |", "| /"]
        d3 = ["|-\\", "| |", "| /"]  # same as d, but different ref
        e = ("----", "--  ", "____")
        self.letterD = BigLetter(d)
        self.letterD2 = BigLetter(d)
        self.letterD3 = BigLetter(d3)
        self.letterE = BigLetter(e)

    def test_add(self):
        dc = copy.copy(self.letterD)
        de = self.letterD + self.letterE
        de2 = self.letterD2
        de2 += self.letterE
        self.assertEqual(de, de2)
        self.assertEqual(dc + self.letterD, self.letterD + dc)

    def test_equality(self):
        self.assertNotEqual(self.letterD, self.letterE)
        # same exact letter
        self.assertEqual(self.letterD, self.letterD)
        # letter made from exact same list
        self.assertEqual(self.letterD, self.letterD2)
        # letter made from different list with same contents
        self.assertEqual(self.letterD, self.letterD3)
        # copied letter
        self.assertEqual(self.letterD, copy.copy(self.letterD))

    def test_rotate(self):
        rr = ['1234', '5678', '9abc']
        rrcw = ['951', 'a62', 'b73', 'c84']
        rrccw = ['48c', '37b', '26a', '159']
        self.assertEqual(BigLetter(rr).rotate(Rotate.cw),
                         BigLetter(rrcw))
        self.assertEqual(BigLetter(rr).rotate(Rotate.ccw),
                         BigLetter(rrccw))
        rlet = BigLetter(rr)
        rcpy = copy.copy(rlet)
        for i in range(4):  # full cw rotation
            rlet.rotate(Rotate.cw)
        self.assertEqual(rlet, rcpy)
        for i in range(4):  # full ccw rotation
            rlet.rotate(Rotate.ccw)
        self.assertEqual(rlet, rcpy)


class BasicBigFontTests(unittest.TestCase):
    def setUp(self):
        pass

    def test_load_and_call(self):
        standard = font_from_file(os.path.join(FONT_DIR, 'standard.flf'))
        self.assertEqual(standard['a'], standard['a'])


class BasicRenderTests(unittest.TestCase):
    def setUp(self):
        pass

    def test_autoload(self):
        rendered = font.render("teststr")


if __name__ == "__main__":
    suites = [unittest.TestLoader().loadTestsFromTestCase(BasicBigLetterTests),
              unittest.TestLoader().loadTestsFromTestCase(BasicBigFontTests),
              unittest.TestLoader().loadTestsFromTestCase(BasicRenderTests)]
    unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(suites))

    if os.name == 'nt':
        raw_input("Press enter to exit.")
