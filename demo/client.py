# client.py

"""Example client script for terminaide.
This script demonstrates how to use terminaide's built-in games.
"""

from terminaide import CursesIndex
from terminaide.terminarcade import play_snake, play_tetris, play_pong


def main():
    # Create the menu structure with actual function references
    menu = [
        {
            "label": "←/→: navigate, Enter: select, Q: quit",
            "options": [
                {"function": play_snake, "title": "Snake"},
                {"function": play_tetris, "title": "Tetris"},
                {"function": play_pong, "title": "Pong"},
            ],
        }
    ]

    # Create and show the menu
    index = CursesIndex(
        menu=menu,
        title="TERMIN-ARCADE",
        epititle="Press Q or ESC in games to return to this menu",
    )

    result = index.show()
    print(f"User selected: {result}")


if __name__ == "__main__":
    main()
