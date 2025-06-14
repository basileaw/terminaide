from terminaide import CursesIndex
from terminaide.terminarcade import snake, tetris, pong

# Test with URL epititle
CursesIndex(
    title="TERMIN-ARCADE",
    subtitle="All the games that are fit to ship.",
    menu=[
        {
            "label": "←/→: navigate, Enter: select, Q: quit",
            "options": [
                {"function": snake, "title": "Snake"},
                {"function": tetris, "title": "Tetris"},
                {"function": pong, "title": "Pong"},
            ],
        }
    ],
    epititle={"text": "View on GitHub", "url": "https://github.com/terminaide/terminaide"},
).show()