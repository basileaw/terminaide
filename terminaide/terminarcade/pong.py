# pong.py

import curses
import random
import signal
import sys

stdscr = None
exit_requested = False


def _pong_game_loop(stdscr_param):
    """Main pong game function that handles the game loop.

    This function manages the overall game flow, including initial setup,
    game loop, and handling exit conditions.

    Args:
        stdscr_param: The curses window.
    """
    global stdscr, exit_requested
    stdscr = stdscr_param
    exit_requested = False

    signal.signal(signal.SIGINT, handle_exit)
    setup_terminal(stdscr)
    my, mx = stdscr.getmaxyx()
    ph, pw = my - 2, mx - 2
    ls = rs = 0  # Left and right scores
    high = 0  # High score

    while True:
        if exit_requested:
            cleanup()
            return

        ls, rs, winner = run_game(stdscr, my, mx, ph, pw, ls, rs, high)

        if exit_requested:
            cleanup()
            return

        cur_score = max(ls, rs)
        high = max(high, cur_score)

        if show_game_over(stdscr, ls, rs, high, my, mx, winner):
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
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_CYAN, -1)
    curses.init_pair(3, curses.COLOR_RED, -1)
    curses.init_pair(4, curses.COLOR_WHITE, -1)
    curses.init_pair(5, curses.COLOR_YELLOW, -1)


def run_game(stdscr, my, mx, ph, pw, ls, rs, high):
    """Run the main pong game loop.

    This function handles all the gameplay mechanics including paddle movement,
    ball physics, collision detection, and scoring.

    Args:
        stdscr: The curses window.
        my, mx: Maximum y and x coordinates.
        ph, pw: Playable height and width.
        ls, rs: Current left and right scores.
        high: Current high score.

    Returns:
        tuple: (left score, right score, winner)
    """
    global exit_requested

    speed = 40  # Even lower value = even faster refresh rate
    inc = 10  # Larger increment = faster speed increases
    min_spd = 15  # Lower minimum speed = faster maximum speed
    win = curses.newwin(ph + 2, pw + 2, 0, 0)
    win.keypad(True)
    win.timeout(speed)

    pad_h = 5
    pad_w = 1
    lpy = ph // 2 - pad_h // 2  # Left paddle y position
    rpy = ph // 2 - pad_h // 2  # Right paddle y position
    lpx = 2  # Left paddle x position
    rpx = pw - 3  # Right paddle x position

    by = ph // 2  # Ball y position
    bx = pw // 2  # Ball x position
    bdy = random.choice([-1, 1])  # Ball y direction
    bdx = random.choice([-1, 1])  # Ball x direction

    winner = None

    # AI difficulty: 1 = easy, 2 = medium, 3 = hard
    ai_difficulty = 2

    draw_screen(stdscr, win, lpy, rpy, lpx, rpx, pad_h, by, bx, ls, rs, high, mx)

    while True:
        if exit_requested:
            cleanup()
            return ls, rs, winner

        key = win.getch()

        # Check for exit key
        if key in (ord("q"), 27):  # q or ESC
            cleanup()
            return ls, rs, winner

        # Handle paddle movement (much faster by moving 4 units)
        if key in [curses.KEY_UP, ord("w"), ord("W")] and lpy > 0:
            lpy -= 4
            # Ensure we don't go out of bounds
            if lpy < 0:
                lpy = 0
        elif key in [curses.KEY_DOWN, ord("s"), ord("S")] and lpy + pad_h < ph:
            lpy += 4
            # Ensure we don't go out of bounds
            if lpy + pad_h > ph:
                lpy = ph - pad_h

        # AI for right paddle (now runs on every frame)
        # Calculate ideal position for right paddle based on ball position
        ideal = by - pad_h // 2

        # Only move every few frames based on difficulty (makes AI beatable)
        if random.randint(1, 5) <= ai_difficulty:
            # Add some predictive movement when ball is moving toward the paddle
            if bdx > 0:
                # Move toward ideal position (much faster movement - 4 units)
                if rpy < ideal and rpy + pad_h < ph:
                    rpy += 4
                    # Prevent going out of bounds
                    if rpy + pad_h > ph:
                        rpy = ph - pad_h
                elif rpy > ideal and rpy > 0:
                    rpy -= 4
                    # Prevent going out of bounds
                    if rpy < 0:
                        rpy = 0
            else:
                # When ball moving away, move toward center more slowly (for easier difficulty)
                center = ph // 2 - pad_h // 2
                if rpy < center and random.randint(0, 2) == 0 and rpy + pad_h < ph:
                    rpy += 2
                elif rpy > center and random.randint(0, 2) == 0 and rpy > 0:
                    rpy -= 2

        # Update ball position with increased speed
        by += bdy * 2  # Multiply by 2 for faster vertical movement
        bx += bdx * 2  # Multiply by 2 for faster horizontal movement

        # Ball collision with top/bottom walls
        # Adjusted to handle faster ball speed
        if by <= 0:
            by = 1
            bdy = abs(bdy)
        elif by >= ph - 1:
            by = ph - 2
            bdy = -abs(bdy)

        # Ball scoring (left/right walls)
        if bx <= 0:
            rs += 1  # Right player scores
            bx, by = pw // 2, ph // 2
            bdx = 1
            bdy = random.choice([-1, 1])
            speed = 80
            win.timeout(speed)
            if rs >= 11:
                winner = "right"
                break
        elif bx >= pw - 1:
            ls += 1  # Left player scores
            bx, by = pw // 2, ph // 2
            bdx = -1
            bdy = random.choice([-1, 1])
            speed = 80
            win.timeout(speed)
            if ls >= 11:
                winner = "left"
                break

        # Ball collision with paddles
        if bx == lpx + pad_w and lpy <= by < lpy + pad_h:
            # Left paddle hit
            bdx = abs(bdx)
            pc = lpy + pad_h // 2
            off = by - pc
            bdy = off // 2
            if speed > min_spd:
                speed -= inc
                win.timeout(speed)
        if bx == rpx - 1 and rpy <= by < rpy + pad_h:
            # Right paddle hit
            bdx = -abs(bdx)
            pc = rpy + pad_h // 2
            off = by - pc
            bdy = off // 2
            if speed > min_spd:
                speed -= inc
                win.timeout(speed)

        # Draw updated game state
        draw_screen(stdscr, win, lpy, rpy, lpx, rpx, pad_h, by, bx, ls, rs, high, mx)

    return ls, rs, winner


def draw_screen(stdscr, win, ly, ry, lx, rx, h, by, bx, ls, rs, hi, mx):
    """Draw the game elements on the screen."""
    win.erase()
    draw_border(win)
    try:
        win.addch(by + 1, bx + 1, ord("*"), curses.color_pair(3) | curses.A_BOLD)
    except:
        curses.error
    try:
        for i in range(h):
            win.addch(
                ly + i + 1, lx + 1, ord("|"), curses.color_pair(1) | curses.A_BOLD
            )
        for i in range(h):
            win.addch(
                ry + i + 1, rx + 1, ord("|"), curses.color_pair(2) | curses.A_BOLD
            )
    except:
        curses.error
    draw_score(stdscr, ls, rs, hi, mx)
    stdscr.noutrefresh()
    win.noutrefresh()
    curses.doupdate()


def draw_border(win):
    """Draw the game border with title."""
    win.box()
    title = "PLAY PONG"
    w = win.getmaxyx()[1]
    if w > len(title) + 4:
        win.addstr(
            0, (w - len(title)) // 2, title, curses.A_BOLD | curses.color_pair(5)
        )


def draw_score(stdscr, ls, rs, hi, mx):
    """Draw the score display at the top of the screen."""
    stdscr.addstr(0, 0, " " * mx)
    stdscr.addstr(0, 2, f" Left: {ls} ", curses.color_pair(5) | curses.A_BOLD)
    stdscr.addstr(0, mx - 14, f" Right: {rs} ", curses.color_pair(5) | curses.A_BOLD)
    ht = f" High: {hi} "
    stdscr.addstr(0, (mx - len(ht)) // 2, ht, curses.color_pair(5) | curses.A_BOLD)


def show_game_over(stdscr, ls, rs, hi, my, mx, winner):
    """Show game over screen and handle restart/quit options.

    Returns:
        bool: True if user chooses to quit, False to restart.
    """
    stdscr.clear()
    cy = my // 2
    wt = "Left Player Wins!" if winner == "left" else "Right Player Wins!"
    data = [
        ("GAME OVER", -3, curses.A_BOLD | curses.color_pair(3)),
        (wt, -1, curses.A_BOLD | curses.color_pair(5)),
        (f"Left Score: {ls} | Right Score: {rs}", 0, curses.color_pair(5)),
        (f"High Score: {hi}", 1, curses.color_pair(5)),
        ("Press 'r' to restart", 3, 0),
        ("Press 'q' to quit", 4, 0),
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
            msg = "Thanks for playing Pong!"
            print("\033[2;{}H{}".format((cols - len(msg)) // 2, msg))
            print("\033[3;{}H{}".format((cols - len("Goodbye!")) // 2, "Goodbye!"))
            sys.stdout.flush()
        except:
            pass


def handle_exit(sig, frame):
    """Handle SIGINT (Ctrl+C) for program exit."""
    global exit_requested
    exit_requested = True


def pong():
    """Run the pong game.

    This is the main public-facing function for launching the pong game.
    """
    try:
        curses.wrapper(_pong_game_loop)
    except Exception as e:
        print(f"\n\033[31mError in pong game: {e}\033[0m")
    finally:
        cleanup()


if __name__ == "__main__":
    print("\033[?25l\033[2J\033[H", end="")
    try:
        pong()
    finally:
        cleanup()
