# client.py

"""Example client script for terminaide.
This script demonstrates how to use terminaide's built-in games.
"""

from terminaide import CursesIndex


def main():
    # Create the same menu structure as terminarcade
    menu = [
        {
            "label": "←/→: navigate, Enter: select, Q: quit",
            "options": [
                {"path": "snake", "title": "Snake"},
                {"path": "tetris", "title": "Tetris"},
                {"path": "pong", "title": "Pong"},
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
