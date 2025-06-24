# client.py

"""Example client script for terminaide.
This script demonstrates how to use terminaide's built-in games.
"""

from terminaide import AutoIndex
from terminarcade import snake, tetris, pong


def main():
    menu = [
        {
            "label": "←/→: navigate, Enter: select, Q: quit",
            "options": [
                {"function": snake, "title": "Snake"},
                {"function": tetris, "title": "Tetris"},
                {"function": pong, "title": "Pong"},
            ],
        }
    ]

    AutoIndex(
        type="curses",
        menu=menu,
        title="TERMIN-ARCADE",
        epititle="Press Q or ESC in games to return to this menu",
    ).show()


if __name__ == "__main__":
    main()
