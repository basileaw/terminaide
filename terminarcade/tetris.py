# tetris.py

import curses
import random
import signal
import sys
import time
import os
from collections import deque

stdscr = None
exit_requested = False

TETROMINOS = [
    [[(0, 0), (0, 1), (0, 2), (0, 3)], [(0, 0), (1, 0), (2, 0), (3, 0)]],
    [[(0, 0), (0, 1), (1, 0), (1, 1)]],
    [
        [(0, 1), (1, 0), (1, 1), (1, 2)],
        [(0, 0), (1, 0), (1, 1), (2, 0)],
        [(0, 0), (0, 1), (0, 2), (1, 1)],
        [(0, 1), (1, 0), (1, 1), (2, 1)],
    ],
    [
        [(0, 0), (1, 0), (2, 0), (2, 1)],
        [(0, 0), (0, 1), (0, 2), (1, 0)],
        [(0, 0), (0, 1), (1, 1), (2, 1)],
        [(0, 2), (1, 0), (1, 1), (1, 2)],
    ],
    [
        [(0, 1), (1, 1), (2, 0), (2, 1)],
        [(0, 0), (1, 0), (1, 1), (1, 2)],
        [(0, 0), (0, 1), (1, 0), (2, 0)],
        [(0, 0), (0, 1), (0, 2), (1, 2)],
    ],
    [[(0, 1), (0, 2), (1, 0), (1, 1)], [(0, 0), (1, 0), (1, 1), (2, 1)]],
    [[(0, 0), (0, 1), (1, 1), (1, 2)], [(0, 1), (1, 0), (1, 1), (2, 0)]],
]
TETROMINO_COLORS = [
    curses.COLOR_CYAN,
    curses.COLOR_YELLOW,
    curses.COLOR_MAGENTA,
    curses.COLOR_WHITE,
    curses.COLOR_BLUE,
    curses.COLOR_GREEN,
    curses.COLOR_RED,
]


def _tetris_game_loop(stdscr_param):
    """Main tetris game function that handles the game loop.

    Args:
        stdscr_param: The curses window.
    """
    global stdscr, exit_requested
    stdscr = stdscr_param
    exit_requested = False

    signal.signal(signal.SIGINT, handle_exit)
    stdscr.clear()
    stdscr.refresh()
    os.system("clear" if os.name == "posix" else "cls")
    setup_terminal(stdscr)
    max_y, max_x = stdscr.getmaxyx()
    high_score = 0

    while True:
        if exit_requested:
            cleanup()
            return

        score = run_game(stdscr, max_y, max_x, high_score)

        if exit_requested:
            cleanup()
            return

        high_score = max(high_score, score)
        if show_game_over(stdscr, score, high_score, max_y, max_x):
            break


def setup_terminal(stdscr):
    """Configure terminal settings for the game."""
    curses.curs_set(0)
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    curses.use_env(False)
    curses.start_color()
    curses.use_default_colors()
    for i, c in enumerate(TETROMINO_COLORS):
        curses.init_pair(i + 1, c, -1)
    curses.init_pair(8, curses.COLOR_WHITE, -1)
    curses.init_pair(9, curses.COLOR_YELLOW, -1)


def run_game(stdscr, max_y, max_x, high_score=0):
    """Run the main tetris game loop.

    Args:
        stdscr: The curses window.
        max_y, max_x: Maximum y and x coordinates.
        high_score: Current high score.

    Returns:
        int: The final score.
    """
    global exit_requested

    board_height = min(20, max_y - 7)
    board_width = min(10, max_x // 2 - 2)
    start_y = 2
    start_x = (max_x - board_width * 2) // 2
    board = [[0 for _ in range(board_width)] for _ in range(board_height)]
    score = 0
    level = 1
    lines_cleared = 0
    game_speed = 500
    game_win = curses.newwin(board_height + 2, board_width * 2 + 2, start_y, start_x)
    game_win.keypad(True)
    game_win.timeout(game_speed)
    piece_type = random.randint(0, len(TETROMINOS) - 1)
    rotation = 0
    pos = [0, board_width // 2 - 1]
    next_piece = random.randint(0, len(TETROMINOS) - 1)
    next_win = curses.newwin(6, 10, start_y, board_width * 2 + start_x + 4)
    fall_time = 0
    last_move = time.time()

    while True:
        if exit_requested:
            return score

        now = time.time()
        delta = now - last_move
        last_move = now
        fall_time += delta * 1000

        key = game_win.getch()

        # Check for exit key
        if key in (ord("q"), 27):  # q or ESC
            return score

        if key in [curses.KEY_LEFT, ord("a"), ord("A")]:
            np = [pos[0], pos[1] - 1]
            if is_valid_position(board, TETROMINOS[piece_type][rotation], np):
                pos = np
        elif key in [curses.KEY_RIGHT, ord("d"), ord("D")]:
            np = [pos[0], pos[1] + 1]
            if is_valid_position(board, TETROMINOS[piece_type][rotation], np):
                pos = np
        elif key in [curses.KEY_DOWN, ord("s"), ord("S")]:
            np = [pos[0] + 1, pos[1]]
            if is_valid_position(board, TETROMINOS[piece_type][rotation], np):
                pos = np
                score += 1
                fall_time = 0
        elif key in [curses.KEY_UP, ord("w"), ord("W")]:
            r = (rotation + 1) % len(TETROMINOS[piece_type])
            if is_valid_position(board, TETROMINOS[piece_type][r], pos):
                rotation = r
        elif key == ord(" "):
            while is_valid_position(
                board, TETROMINOS[piece_type][rotation], [pos[0] + 1, pos[1]]
            ):
                pos[0] += 1
                score += 2
            fall_time = game_speed + 1

        if fall_time >= game_speed:
            np = [pos[0] + 1, pos[1]]
            if is_valid_position(board, TETROMINOS[piece_type][rotation], np):
                pos = np
            else:
                place_tetromino(
                    board, TETROMINOS[piece_type][rotation], pos, piece_type + 1
                )
                c = clear_lines(board)
                if c > 0:
                    lines_cleared += c
                    score += calculate_score(c, level)
                    level = lines_cleared // 10 + 1
                    game_speed = max(100, 500 - (level - 1) * 50)
                    game_win.timeout(game_speed)
                piece_type = next_piece
                rotation = 0
                pos = [0, board_width // 2 - 1]
                next_piece = random.randint(0, len(TETROMINOS) - 1)
                if not is_valid_position(board, TETROMINOS[piece_type][rotation], pos):
                    return score
            fall_time = 0

        draw_game(
            stdscr,
            game_win,
            next_win,
            board,
            TETROMINOS[piece_type][rotation],
            pos,
            piece_type,
            next_piece,
            score,
            level,
            lines_cleared,
            high_score,
            board_height,
            board_width,
            max_x,
            start_y,
            start_x,
        )


def is_valid_position(board, piece, pos):
    """Check if the tetromino position is valid.

    Args:
        board: Game board state.
        piece: Tetromino piece shape.
        pos: Position [y, x] to check.

    Returns:
        bool: True if position is valid, False otherwise.
    """
    bh = len(board)
    bw = len(board[0])
    for y, x in piece:
        ny = pos[0] + y
        nx = pos[1] + x
        if nx < 0 or nx >= bw or ny >= bh:
            return False
        if ny >= 0 and board[ny][nx] != 0:
            return False
    return True


def place_tetromino(board, piece, pos, t):
    """Place a tetromino on the board.

    Args:
        board: Game board state.
        piece: Tetromino piece shape.
        pos: Position [y, x] to place.
        t: Tetromino type (for color).
    """
    for y, x in piece:
        ny = pos[0] + y
        nx = pos[1] + x
        if ny >= 0:
            board[ny][nx] = t


def clear_lines(board):
    """Clear completed lines and calculate score.

    Args:
        board: Game board state.

    Returns:
        int: Number of lines cleared.
    """
    bh = len(board)
    bw = len(board[0])
    c = 0
    y = bh - 1
    while y >= 0:
        if all(board[y][x] != 0 for x in range(bw)):
            for y2 in range(y, 0, -1):
                for x in range(bw):
                    board[y2][x] = board[y2 - 1][x]
            for x in range(bw):
                board[0][x] = 0
            c += 1
        else:
            y -= 1
    return c


def calculate_score(lines, level):
    """Calculate score based on lines cleared and level.

    Args:
        lines: Number of lines cleared at once.
        level: Current level.

    Returns:
        int: Score to add.
    """
    s = [0, 100, 300, 500, 800]
    return s[min(lines, 4)] * level


def safe_addstr(stdscr, y, x, text, attr=0):
    """Safely add a string to the screen, handling boundary conditions.

    Args:
        stdscr: The screen to draw on.
        y, x: Coordinates to start drawing.
        text: Text to draw.
        attr: Text attributes.
    """
    h, w = stdscr.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    ml = w - x
    if ml <= 0:
        return
    t = text[:ml]
    try:
        stdscr.addstr(y, x, t, attr)
    except:
        curses.error


def draw_game(
    stdscr,
    gw,
    nw,
    board,
    piece,
    pos,
    ptype,
    ntype,
    score,
    level,
    lines,
    high_score,
    bh,
    bw,
    mx,
    sy,
    sx,
):
    """Draw the game screen with all elements.

    Args:
        stdscr: Main screen.
        gw: Game window.
        nw: Next piece window.
        board: Game board state.
        piece: Current tetromino shape.
        pos: Current position [y, x].
        ptype: Current piece type.
        ntype: Next piece type.
        score: Current score.
        level: Current level.
        lines: Lines cleared.
        high_score: High score.
        bh, bw: Board height and width.
        mx: Max x coordinate.
        sy, sx: Start y and x coordinates.
    """
    gw.erase()
    nw.erase()
    gw.box()
    nw.box()
    t = "PLAY TETRIS"
    ww = gw.getmaxyx()[1]
    if ww > len(t) + 4:
        gw.addstr(0, (ww - len(t)) // 2, t, curses.A_BOLD | curses.color_pair(9))
    nw.addstr(0, 1, "NEXT", curses.A_BOLD | curses.color_pair(9))
    for y in range(bh):
        for x in range(bw):
            c = board[y][x]
            if c != 0:
                try:
                    gw.addstr(
                        y + 1, x * 2 + 1, "[]", curses.color_pair(c) | curses.A_BOLD
                    )
                except:
                    curses.error
    for y, x in piece:
        ny = pos[0] + y
        nx = pos[1] + x
        if ny >= 0:
            try:
                gw.addstr(
                    ny + 1,
                    nx * 2 + 1,
                    "[]",
                    curses.color_pair(ptype + 1) | curses.A_BOLD,
                )
            except:
                curses.error
    nt = TETROMINOS[ntype][0]
    minx = min(a for _, a in nt)
    maxx = max(a for _, a in nt)
    miny = min(a for a, _ in nt)
    maxy = max(a for a, _ in nt)
    cy = 3
    cx = 5
    for yy, xx in nt:
        dy = cy + yy - (miny + maxy) // 2
        dx = cx + (xx - (minx + maxx) // 2) * 2
        try:
            nw.addstr(dy, dx, "[]", curses.color_pair(ntype + 1) | curses.A_BOLD)
        except:
            curses.error
    safe_addstr(stdscr, 0, 0, " " * mx)
    st = f" Score: {score} "
    lt = f" Level: {level} "
    hi = f" High: {high_score} "
    safe_addstr(stdscr, 0, 2, st, curses.color_pair(9) | curses.A_BOLD)
    safe_addstr(stdscr, 0, 2 + len(st) + 2, lt, curses.color_pair(9) | curses.A_BOLD)
    sw = stdscr.getmaxyx()[1]
    hx = min(sw - len(hi) - 1, mx - len(hi) - 2)
    safe_addstr(stdscr, 0, hx, hi, curses.color_pair(9) | curses.A_BOLD)
    # Controls below the board window
    ctrl = "↑:Rotate  ←→:Move  ↓:Drop  Space:Hard Drop  Q:Quit"
    controls_row = sy + bh + 3  # Just a few lines below bottom of game board
    controls_col = sx + ((bw * 2 + 2) - len(ctrl)) // 2
    safe_addstr(stdscr, controls_row, controls_col, ctrl)

    stdscr.noutrefresh()
    gw.noutrefresh()
    nw.noutrefresh()
    curses.doupdate()


def show_game_over(stdscr, score, high_score, my, mx):
    """Show game over screen and handle restart/quit options.

    Args:
        stdscr: The screen to draw on.
        score: Final score.
        high_score: High score.
        my, mx: Maximum y and x coordinates.

    Returns:
        bool: True if user chooses to quit, False to restart.
    """
    stdscr.clear()
    cy = my // 2
    data = [
        ("GAME OVER", -3, curses.A_BOLD | curses.color_pair(3)),
        (f"Your Score: {score}", -1, curses.color_pair(9)),
        (f"High Score: {high_score}", 0, curses.color_pair(9)),
        ("Press 'r' to restart", 2, 0),
        ("Press 'q' to quit", 3, 0),
    ]
    for txt, yo, attr in data:
        stdscr.addstr(cy + yo, mx // 2 - len(txt) // 2, txt, attr)
    stdscr.noutrefresh()
    curses.doupdate()
    stdscr.nodelay(False)
    while True:
        k = stdscr.getch()
        if k == ord("q"):
            return True
        if k == ord("r"):
            return False


def cleanup():
    """Clean up terminal state when exiting."""
    if stdscr:
        try:
            curses.endwin()
            print("\033[?25l\033[2J\033[H", end="")
            try:
                rows, cols = stdscr.getmaxyx()
            except:
                rows, cols = 24, 80
            msg = "Thanks for playing Tetris!"
            print("\033[2;{}H{}".format((cols - len(msg)) // 2, msg))
            print("\033[3;{}H{}".format((cols - len("Goodbye!")) // 2, "Goodbye!"))
            sys.stdout.flush()
        except:
            pass


def handle_exit(sig, frame):
    """Handle SIGINT (Ctrl+C) for program exit."""
    global exit_requested
    exit_requested = True


def tetris():
    """Run the tetris game.

    This is the main public-facing function for launching the tetris game.
    """
    try:
        os.system("clear" if os.name == "posix" else "cls")
        print("\033[2J\033[H", end="")
        sys.stdout.flush()
        curses.wrapper(_tetris_game_loop)
    except Exception as e:
        print(f"\n\033[31mError in tetris game: {e}\033[0m")
    finally:
        cleanup()


if __name__ == "__main__":
    print("\033[?25l\033[2J\033[H", end="")
    sys.stdout.flush()
    os.system("clear" if os.name == "posix" else "cls")
    try:
        tetris()
    finally:
        cleanup()
