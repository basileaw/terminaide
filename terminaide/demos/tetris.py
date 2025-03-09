# terminaide/demos/tetris.py

"""
Tetris game demo for terminaide.

This module provides a playable Tetris game in the terminal.
It's designed to match the style of other built-in demos for the terminaide package.
"""

import curses
import random
import signal
import sys
import time
from collections import deque

_stdscr = None
_exit_requested = False  # Set by the SIGINT handler when Ctrl+C is pressed.

# Define the tetromino shapes using (y, x) coordinates
TETROMINOS = [
    # I
    [[(0, 0), (0, 1), (0, 2), (0, 3)], 
     [(0, 0), (1, 0), (2, 0), (3, 0)]],
    # O
    [[(0, 0), (0, 1), (1, 0), (1, 1)]],
    # T
    [[(0, 1), (1, 0), (1, 1), (1, 2)],
     [(0, 0), (1, 0), (1, 1), (2, 0)],
     [(0, 0), (0, 1), (0, 2), (1, 1)],
     [(0, 1), (1, 0), (1, 1), (2, 1)]],
    # L
    [[(0, 0), (1, 0), (2, 0), (2, 1)],
     [(0, 0), (0, 1), (0, 2), (1, 0)],
     [(0, 0), (0, 1), (1, 1), (2, 1)],
     [(0, 2), (1, 0), (1, 1), (1, 2)]],
    # J
    [[(0, 1), (1, 1), (2, 0), (2, 1)],
     [(0, 0), (1, 0), (1, 1), (1, 2)],
     [(0, 0), (0, 1), (1, 0), (2, 0)],
     [(0, 0), (0, 1), (0, 2), (1, 2)]],
    # S
    [[(0, 1), (0, 2), (1, 0), (1, 1)],
     [(0, 0), (1, 0), (1, 1), (2, 1)]],
    # Z
    [[(0, 0), (0, 1), (1, 1), (1, 2)],
     [(0, 1), (1, 0), (1, 1), (2, 0)]]
]

# Define colors for tetrominoes
TETROMINO_COLORS = [
    curses.COLOR_CYAN,    # I
    curses.COLOR_YELLOW,  # O
    curses.COLOR_MAGENTA, # T
    curses.COLOR_WHITE,   # L
    curses.COLOR_BLUE,    # J
    curses.COLOR_GREEN,   # S
    curses.COLOR_RED      # Z
]

def tetris(stdscr):
    """Main entry point for the Tetris game."""
    global _stdscr
    _stdscr = stdscr
    signal.signal(signal.SIGINT, handle_exit)
    setup_terminal(stdscr)

    max_y, max_x = stdscr.getmaxyx()
    high_score = 0

    while True:
        if _exit_requested:
            cleanup()
            return
        score = run_game(stdscr, max_y, max_x, high_score)
        if _exit_requested:
            cleanup()
            return
        high_score = max(high_score, score)
        if show_game_over(stdscr, score, high_score, max_y, max_x):
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
    
    # Initialize colors for each tetromino type
    for i, color in enumerate(TETROMINO_COLORS):
        curses.init_pair(i + 1, color, -1)
    
    # Additional color pairs
    curses.init_pair(8, curses.COLOR_WHITE, -1)  # Border
    curses.init_pair(9, curses.COLOR_YELLOW, -1) # Score

def run_game(stdscr, max_y, max_x, high_score=0):
    """Run one complete game session; return the score."""
    global _exit_requested
    
    # Game board dimensions (playable area)
    board_height = min(20, max_y - 4)
    board_width = min(10, max_x // 2 - 2)
    
    # Start position for the board (centered)
    start_y = 2
    start_x = (max_x - board_width * 2) // 2
    
    # Create game board (0 = empty, 1-7 = tetromino type)
    board = [[0 for _ in range(board_width)] for _ in range(board_height)]
    
    # Game state variables
    score = 0
    level = 1
    lines_cleared = 0
    game_speed = 500  # milliseconds
    
    # Current tetromino state
    current_piece = None
    current_rotation = 0
    current_pos = [0, 0]
    
    # Create game window
    game_win = curses.newwin(board_height + 2, board_width * 2 + 2, start_y, start_x)
    game_win.keypad(True)
    game_win.timeout(game_speed)
    
    # Generate first piece
    current_piece, current_rotation, current_pos = new_tetromino(board_width)
    next_piece = random.randint(0, len(TETROMINOS) - 1)
    
    # Next piece window
    next_win = curses.newwin(6, 10, start_y, start_x + board_width * 2 + 4)
    
    # Game loop
    fall_time = 0
    last_move_time = time.time()
    
    while True:
        if _exit_requested:
            return score
        
        current_time = time.time()
        delta_time = current_time - last_move_time
        last_move_time = current_time
        fall_time += delta_time * 1000  # Convert to milliseconds
        
        # Handle input
        key = game_win.getch()
        
        if key in (ord('q'), 27):  # q or ESC
            return score
            
        # Handle movement
        moved = False
        if key in [curses.KEY_LEFT, ord('a'), ord('A')]:
            # Move left if possible
            new_pos = [current_pos[0], current_pos[1] - 1]
            if is_valid_position(board, TETROMINOS[current_piece][current_rotation], new_pos):
                current_pos = new_pos
                moved = True
                
        elif key in [curses.KEY_RIGHT, ord('d'), ord('D')]:
            # Move right if possible
            new_pos = [current_pos[0], current_pos[1] + 1]
            if is_valid_position(board, TETROMINOS[current_piece][current_rotation], new_pos):
                current_pos = new_pos
                moved = True
                
        elif key in [curses.KEY_DOWN, ord('s'), ord('S')]:
            # Move down if possible (soft drop)
            new_pos = [current_pos[0] + 1, current_pos[1]]
            if is_valid_position(board, TETROMINOS[current_piece][current_rotation], new_pos):
                current_pos = new_pos
                score += 1  # Bonus for soft drop
                moved = True
                fall_time = 0
        
        elif key in [curses.KEY_UP, ord('w'), ord('W')]:
            # Rotate if possible
            new_rotation = (current_rotation + 1) % len(TETROMINOS[current_piece])
            if is_valid_position(board, TETROMINOS[current_piece][new_rotation], current_pos):
                current_rotation = new_rotation
                moved = True
                
        elif key == ord(' '):
            # Hard drop
            while is_valid_position(board, TETROMINOS[current_piece][current_rotation], 
                                   [current_pos[0] + 1, current_pos[1]]):
                current_pos[0] += 1
                score += 2  # Bonus for hard drop
            
            # Force immediate placement
            fall_time = game_speed + 1
        
        # Handle automatic falling
        if fall_time >= game_speed:
            # Try to move down
            new_pos = [current_pos[0] + 1, current_pos[1]]
            if is_valid_position(board, TETROMINOS[current_piece][current_rotation], new_pos):
                current_pos = new_pos
            else:
                # Lock piece in place
                place_tetromino(board, TETROMINOS[current_piece][current_rotation], 
                               current_pos, current_piece + 1)
                
                # Check for completed lines
                cleared = clear_lines(board)
                if cleared > 0:
                    lines_cleared += cleared
                    score += calculate_score(cleared, level)
                    
                    # Update level
                    level = lines_cleared // 10 + 1
                    game_speed = max(100, 500 - (level - 1) * 50)
                    game_win.timeout(game_speed)
                
                # Get next piece
                current_piece = next_piece
                current_rotation = 0
                current_pos = [0, board_width // 2 - 1]
                next_piece = random.randint(0, len(TETROMINOS) - 1)
                
                # Check for game over
                if not is_valid_position(board, TETROMINOS[current_piece][current_rotation], current_pos):
                    return score
            
            fall_time = 0
        
        # Update display
        draw_game(stdscr, game_win, next_win, board, TETROMINOS[current_piece][current_rotation], 
                 current_pos, current_piece, next_piece, score, level, lines_cleared, high_score, 
                 board_height, board_width, max_x)
    
    return score

def new_tetromino(board_width):
    """Generate a new random tetromino."""
    piece_type = random.randint(0, len(TETROMINOS) - 1)
    rotation = 0
    # Start position (top center)
    pos = [0, board_width // 2 - 1]
    return piece_type, rotation, pos

def is_valid_position(board, piece, pos):
    """Check if the piece can be placed at the given position."""
    board_height = len(board)
    board_width = len(board[0])
    
    for y, x in piece:
        new_y = pos[0] + y
        new_x = pos[1] + x
        
        # Check boundaries
        if new_x < 0 or new_x >= board_width or new_y >= board_height:
            return False
            
        # Check for collision with existing pieces
        if new_y >= 0 and board[new_y][new_x] != 0:
            return False
            
    return True

def place_tetromino(board, piece, pos, piece_type):
    """Place the tetromino on the board."""
    for y, x in piece:
        new_y = pos[0] + y
        new_x = pos[1] + x
        if new_y >= 0:  # Don't place blocks above the board
            board[new_y][new_x] = piece_type

def clear_lines(board):
    """Clear completed lines and return the number of lines cleared."""
    board_height = len(board)
    board_width = len(board[0])
    lines_cleared = 0
    
    # Check each row from bottom to top
    y = board_height - 1
    while y >= 0:
        if all(board[y][x] != 0 for x in range(board_width)):
            # Move all rows above down by one
            for y2 in range(y, 0, -1):
                for x in range(board_width):
                    board[y2][x] = board[y2-1][x]
            
            # Clear the top row
            for x in range(board_width):
                board[0][x] = 0
                
            lines_cleared += 1
        else:
            y -= 1
    
    return lines_cleared

def calculate_score(lines, level):
    """Calculate score based on lines cleared and level."""
    line_scores = [0, 100, 300, 500, 800]  # 0, 1, 2, 3, 4+ lines
    return line_scores[min(lines, 4)] * level

def safe_addstr(stdscr, y, x, text, attr=0):
    """Safely add a string to the screen, avoiding edge errors."""
    height, width = stdscr.getmaxyx()
    
    # Check if the position is valid
    if y < 0 or y >= height or x < 0 or x >= width:
        return
    
    # Truncate text if it would go off the screen
    max_len = width - x
    if max_len <= 0:
        return
    
    display_text = text[:max_len]
    
    try:
        stdscr.addstr(y, x, display_text, attr)
    except curses.error:
        # Ignore any remaining errors (like trying to write to the bottom-right cell)
        pass

def draw_game(stdscr, game_win, next_win, board, current_piece, current_pos, 
             current_type, next_type, score, level, lines, high_score, 
             board_height, board_width, max_x):
    """Draw the game screen."""
    # Clear windows
    game_win.erase()
    next_win.erase()
    
    # Draw border and title
    game_win.box()
    next_win.box()
    
    title = "TETRIS"
    w = game_win.getmaxyx()[1]
    if w > len(title) + 4:
        game_win.addstr(0, (w - len(title)) // 2, title, curses.A_BOLD | curses.color_pair(9))
    
    next_win.addstr(0, 1, "NEXT", curses.A_BOLD | curses.color_pair(9))
    
    # Draw board
    for y in range(board_height):
        for x in range(board_width):
            cell = board[y][x]
            if cell != 0:
                # Draw filled cells with the appropriate color
                try:
                    game_win.addstr(y + 1, x * 2 + 1, "[]", curses.color_pair(cell) | curses.A_BOLD)
                except curses.error:
                    pass
    
    # Draw current piece
    for y, x in current_piece:
        new_y = current_pos[0] + y
        new_x = current_pos[1] + x
        if new_y >= 0:  # Only draw if on the visible board
            try:
                game_win.addstr(new_y + 1, new_x * 2 + 1, "[]", 
                               curses.color_pair(current_type + 1) | curses.A_BOLD)
            except curses.error:
                pass
    
    # Draw next piece
    next_tetromino = TETROMINOS[next_type][0]
    # Find the bounding box of the next piece
    min_x = min(x for _, x in next_tetromino)
    max_x = max(x for _, x in next_tetromino)
    min_y = min(y for y, _ in next_tetromino)
    max_y = max(y for y, _ in next_tetromino)
    
    # Center in the next window
    center_y = 3
    center_x = 5
    
    for y, x in next_tetromino:
        # Adjust to center
        display_y = center_y + y - (min_y + max_y) // 2
        display_x = center_x + (x - (min_x + max_x) // 2) * 2
        
        try:
            next_win.addstr(display_y, display_x, "[]", 
                           curses.color_pair(next_type + 1) | curses.A_BOLD)
        except curses.error:
            pass
    
    # Draw score and other info - use the safe_addstr function
    safe_addstr(stdscr, 0, 0, " " * max_x)
    score_text = f" Score: {score} "
    level_text = f" Level: {level} "
    lines_text = f" Lines: {lines} "
    high_text = f" High: {high_score} "
    
    safe_addstr(stdscr, 0, 2, score_text, curses.color_pair(9) | curses.A_BOLD)
    safe_addstr(stdscr, 0, 2 + len(score_text) + 2, level_text, curses.color_pair(9) | curses.A_BOLD)
    
    # Calculate a safe position for the high score that won't go off-screen
    stdscr_width = stdscr.getmaxyx()[1]
    high_x = min(stdscr_width - len(high_text) - 1, max_x - len(high_text) - 2)
    safe_addstr(stdscr, 0, high_x, high_text, curses.color_pair(9) | curses.A_BOLD)
    
    # Controls reminder at the bottom - use safe_addstr
    controls = "↑:Rotate  ←→:Move  ↓:Soft Drop  Space:Hard Drop  Q:Quit"
    if stdscr.getmaxyx()[0] > board_height + 3:
        safe_addstr(stdscr, board_height + 3, (max_x - len(controls)) // 2, controls)
    
    # Refresh all windows
    stdscr.noutrefresh()
    game_win.noutrefresh()
    next_win.noutrefresh()
    curses.doupdate()

def show_game_over(stdscr, score, high_score, max_y, max_x):
    """Show game over screen and handle restart/quit."""
    stdscr.clear()
    cy = max_y // 2
    
    data = [
        ("GAME OVER", -3, curses.A_BOLD | curses.color_pair(3)),
        (f"Your Score: {score}", -1, curses.color_pair(9)),
        (f"High Score: {high_score}", 0, curses.color_pair(9)),
        ("Press 'r' to restart", 2, 0),
        ("Press 'q' to quit", 3, 0),
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
            msg = "Thanks for playing Tetris!"
            print("\033[2;{}H{}".format((cols - len(msg)) // 2, msg))
            print("\033[3;{}H{}".format((cols - len("Goodbye!")) // 2, "Goodbye!"))
            sys.stdout.flush()
        except:
            pass

def handle_exit(sig, frame):
    """Set exit flag on Ctrl+C instead of raising KeyboardInterrupt."""
    global _exit_requested
    _exit_requested = True

def run_demo():
    """Entry point for running the demo from elsewhere."""
    try:
        curses.wrapper(tetris)
    except Exception as e:
        print(f"\n\033[31mError in demo: {e}\033[0m")
    finally:
        cleanup()

if __name__ == "__main__":
    # Set cursor to invisible using ansi 
    print("\033[?25l\033[2J\033[H", end="")
    try:
        curses.wrapper(tetris)
    finally:
        cleanup()