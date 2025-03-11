# terminaide/demos/pong.py

"""
Pong demo for terminaide.

This module provides a playable Pong game in the terminal.
It's one of the built-in demos for the terminaide package.
"""

import curses
import random
import signal
import sys
import time

_stdscr = None
exit_requested = False  # Set by the SIGINT handler when Ctrl+C is pressed.

def pong(stdscr):
    """Main entry point for the Pong demo."""
    global _stdscr
    _stdscr = stdscr
    signal.signal(signal.SIGINT, handle_exit)
    setup_terminal(stdscr)
    max_y, max_x = stdscr.getmaxyx()
    play_height, play_width = max_y - 2, max_x - 2
    
    # Initialize scores
    left_score = right_score = 0
    high_score = 0
    
    while True:
        if exit_requested:
            cleanup()
            return
        
        left_score, right_score, winner = run_game(stdscr, max_y, max_x, play_height, play_width, 
                                                  left_score, right_score, high_score)
        
        if exit_requested:
            cleanup()
            return
        
        current_score = max(left_score, right_score)
        high_score = max(high_score, current_score)
        
        if show_game_over(stdscr, left_score, right_score, high_score, max_y, max_x, winner):
            break

def setup_terminal(stdscr):
    """Configure terminal settings."""
    curses.curs_set(0)
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)
    curses.use_env(False)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)  # Left paddle
    curses.init_pair(2, curses.COLOR_CYAN, -1)   # Right paddle
    curses.init_pair(3, curses.COLOR_RED, -1)    # Ball
    curses.init_pair(4, curses.COLOR_WHITE, -1)  # Border
    curses.init_pair(5, curses.COLOR_YELLOW, -1) # Score

def run_game(stdscr, max_y, max_x, ph, pw, left_score, right_score, high_score):
    """Run one complete game session; return the scores and winner."""
    global exit_requested
    
    # Game parameters
    game_speed = 80
    ball_speed_increase = 5
    min_game_speed = 40
    
    # Create game window
    game_win = curses.newwin(ph + 2, pw + 2, 0, 0)
    game_win.keypad(True)
    game_win.timeout(game_speed)
    
    # Paddle dimensions and positions
    paddle_height = 5
    paddle_width = 1
    left_pad_y = ph // 2 - paddle_height // 2
    right_pad_y = ph // 2 - paddle_height // 2
    left_pad_x = 2
    right_pad_x = pw - 3
    
    # Ball position and velocity
    ball_y = ph // 2
    ball_x = pw // 2
    ball_dy = random.choice([-1, 1])
    ball_dx = random.choice([-1, 1])
    
    # Game state
    winner = None
    
    # Draw initial screen
    draw_screen(stdscr, game_win, left_pad_y, right_pad_y, left_pad_x, right_pad_x, 
               paddle_height, ball_y, ball_x, left_score, right_score, high_score, max_x)
    
    while True:
        if exit_requested:
            cleanup()
            return left_score, right_score, winner
        
        # Get user input
        key = game_win.getch()
        
        if key in (ord('q'), 27):  # q or ESC
            cleanup()
            return left_score, right_score, winner
        
        # Move paddles
        if key in [curses.KEY_UP, ord('w'), ord('W')] and left_pad_y > 0:
            left_pad_y -= 1
        elif key in [curses.KEY_DOWN, ord('s'), ord('S')] and left_pad_y + paddle_height < ph:
            left_pad_y += 1
            
        # Simple AI for right paddle (or use arrow keys for 2-player)
        if key == ord('1'):  # 1-player mode (AI)
            if ball_dx > 0:  # Only move if ball is coming towards AI
                # Calculate ideal position - follow the ball with a slight delay
                ideal_pos = ball_y - paddle_height // 2
                if right_pad_y < ideal_pos and right_pad_y + paddle_height < ph:
                    right_pad_y += 1
                elif right_pad_y > ideal_pos and right_pad_y > 0:
                    right_pad_y -= 1
        else:  # 2-player mode
            if key in [ord('i'), ord('I')] and right_pad_y > 0:
                right_pad_y -= 1
            elif key in [ord('k'), ord('K')] and right_pad_y + paddle_height < ph:
                right_pad_y += 1
        
        # Update ball position
        ball_y += ball_dy
        ball_x += ball_dx
        
        # Check for collision with top/bottom wall
        if ball_y <= 0:
            ball_y = 1
            ball_dy = abs(ball_dy)  # Bounce down
            
        elif ball_y >= ph - 1:
            ball_y = ph - 2
            ball_dy = -abs(ball_dy)  # Bounce up
        
        # Check for scoring
        if ball_x <= 0:
            right_score += 1
            ball_x, ball_y = pw // 2, ph // 2
            ball_dx = 1
            ball_dy = random.choice([-1, 1])
            game_speed = 80  # Reset speed
            game_win.timeout(game_speed)
            
            if right_score >= 11:  # Game ends at 11 points
                winner = "right"
                break
                
        elif ball_x >= pw - 1:
            left_score += 1
            ball_x, ball_y = pw // 2, ph // 2
            ball_dx = -1
            ball_dy = random.choice([-1, 1])
            game_speed = 80  # Reset speed
            game_win.timeout(game_speed)
            
            if left_score >= 11:  # Game ends at 11 points
                winner = "left"
                break
        
        # Check for paddle collisions
        # Left paddle
        if (ball_x == left_pad_x + paddle_width and 
            left_pad_y <= ball_y < left_pad_y + paddle_height):
            ball_dx = abs(ball_dx)  # Bounce right
            
            # Adjust angle based on where ball hits paddle
            paddle_center = left_pad_y + paddle_height // 2
            offset = ball_y - paddle_center
            ball_dy = offset // 2  # -2, -1, 0, 1, or 2
            
            # Increase speed slightly
            if game_speed > min_game_speed:
                game_speed -= ball_speed_increase
                game_win.timeout(game_speed)
        
        # Right paddle
        if (ball_x == right_pad_x - 1 and 
            right_pad_y <= ball_y < right_pad_y + paddle_height):
            ball_dx = -abs(ball_dx)  # Bounce left
            
            # Adjust angle based on where ball hits paddle
            paddle_center = right_pad_y + paddle_height // 2
            offset = ball_y - paddle_center
            ball_dy = offset // 2  # -2, -1, 0, 1, or 2
            
            # Increase speed slightly
            if game_speed > min_game_speed:
                game_speed -= ball_speed_increase
                game_win.timeout(game_speed)
        
        # Update display
        draw_screen(stdscr, game_win, left_pad_y, right_pad_y, left_pad_x, right_pad_x, 
                   paddle_height, ball_y, ball_x, left_score, right_score, high_score, max_x)
    
    return left_score, right_score, winner

def draw_screen(stdscr, win, left_y, right_y, left_x, right_x, paddle_height, 
               ball_y, ball_x, left_score, right_score, high_score, max_x):
    """Draw the game screen."""
    win.erase()
    draw_border(win)
    
    # Draw ball
    try:
        win.addch(ball_y + 1, ball_x + 1, ord('*'), curses.color_pair(3) | curses.A_BOLD)
    except curses.error:
        pass
    
    # Draw paddles
    try:
        # Left paddle
        for i in range(paddle_height):
            win.addch(left_y + i + 1, left_x + 1, ord('|'), curses.color_pair(1) | curses.A_BOLD)
        
        # Right paddle
        for i in range(paddle_height):
            win.addch(right_y + i + 1, right_x + 1, ord('|'), curses.color_pair(2) | curses.A_BOLD)
    except curses.error:
        pass
    
    # Draw score
    draw_score(stdscr, left_score, right_score, high_score, max_x)
    
    # Refresh display
    stdscr.noutrefresh()
    win.noutrefresh()
    curses.doupdate()

def draw_border(win):
    """Draw border around the game window."""
    win.box()
    title = "PONG GAME"
    w = win.getmaxyx()[1]
    if w > len(title) + 4:
        win.addstr(0, (w - len(title)) // 2, title, curses.A_BOLD | curses.color_pair(5))

def draw_score(stdscr, left_score, right_score, high_score, max_x):
    """Draw score at the top of the screen."""
    stdscr.addstr(0, 0, " " * max_x)
    stdscr.addstr(0, 2, f" Left: {left_score} ", curses.color_pair(5) | curses.A_BOLD)
    stdscr.addstr(0, max_x - 14, f" Right: {right_score} ", curses.color_pair(5) | curses.A_BOLD)
    
    # High score in the middle
    high_txt = f" High: {high_score} "
    stdscr.addstr(0, (max_x - len(high_txt)) // 2, high_txt, curses.color_pair(5) | curses.A_BOLD)

def show_game_over(stdscr, left_score, right_score, high_score, max_y, max_x, winner):
    """Show game over screen and handle restart/quit."""
    stdscr.clear()
    cy = max_y // 2
    
    winner_text = f"Left Player Wins!" if winner == "left" else "Right Player Wins!"
    
    data = [
        ("GAME OVER", -3, curses.A_BOLD | curses.color_pair(3)),
        (winner_text, -1, curses.A_BOLD | curses.color_pair(5)),
        (f"Left Score: {left_score} | Right Score: {right_score}", 0, curses.color_pair(5)),
        (f"High Score: {high_score}", 1, curses.color_pair(5)),
        ("Press 'r' to restart", 3, 0),
        ("Press 'q' to quit", 4, 0),
    ]
    
    for txt, yo, attr in data:
        stdscr.addstr(cy + yo, max_x // 2 - len(txt) // 2, txt, attr)
    
    stdscr.noutrefresh()
    curses.doupdate()
    stdscr.nodelay(False)
    
    while True:
        key = stdscr.getch()
        if key == ord('q'):
            return True
        if key == ord('r'):
            return False

def cleanup():
    """Restore terminal state and print goodbye message."""
    if _stdscr is not None:
        try:
            curses.endwin()
            print("\033[?25l\033[2J\033[H", end="")  # Clear screen
            try:
                rows, cols = _stdscr.getmaxyx()
            except:
                rows, cols = 24, 80
            msg = "Thanks for playing Pong!"
            print("\033[2;{}H{}".format((cols - len(msg)) // 2, msg))
            print("\033[3;{}H{}".format((cols - len("Goodbye!")) // 2, "Goodbye!"))
            sys.stdout.flush()
        except:
            pass

def handle_exit(sig, frame):
    """Set exit flag on Ctrl+C instead of raising KeyboardInterrupt."""
    global exit_requested
    exit_requested = True

def run_demo():
    """Entry point for running the demo from elsewhere."""
    try:
        curses.wrapper(pong)
    except Exception as e:
        print(f"\n\033[31mError in demo: {e}\033[0m")
    finally:
        cleanup()

if __name__ == "__main__":
    # Set cursor to invisible using ansi 
    print("\033[?25l\033[2J\033[H", end="")
    try:
        curses.wrapper(pong)
    finally:
        cleanup()