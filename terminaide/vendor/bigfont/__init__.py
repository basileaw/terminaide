"""bigfont, a pure python library for rendering large fonts in a console
using fixed-width console characters.

Simple usage:

  import bigfont
  bigfont.bigprint("hello")

This loads the first default font from those included in the fonts
directory of this library, and prints it.

To load a specific font from an flf file:

  from font import font_from_file
  myfont = font_from_file('path_to_myfont.flf')
  myfont.bigprint("hello, myfont")
  mystrvar = myfont.render("i will print this myself")
  print(mystrvar)

More fonts can be obtained from:
http://www.jave.de/figlet/fonts.html
"""

__version__ = "0.1.0"

from .font import BigFont
from .font import font_from_file
from .font import render
from .font import bigprint
from . import basic_tests
