# terminal_snake.py

import curses
import random
import signal
import sys
from collections import deque

# Global reference for cleanup
_stdscr = None

def main(stdscr):
    """Main entry point for the Snake game."""
    global _stdscr
    _stdscr = stdscr
    
    # Setup signal handler and terminal
    signal.signal(signal.SIGINT, handle_exit)
    setup_terminal(stdscr)
    
    # Get screen dimensions
    max_y, max_x = stdscr.getmaxyx()
    play_height, play_width = max_y - 2, max_x - 2
    
    # Main game loop with restart capability
    high_score = 0
    while True:
        score = run_game(stdscr, max_y, max_x, play_height, play_width, high_score)
        high_score = max(high_score, score)
        if show_game_over(stdscr, score, high_score, max_y, max_x):
            break

def setup_terminal(stdscr):
    """Configure terminal settings."""
    curses.curs_set(0)          # Hide cursor
    curses.noecho()             # Don't echo keypresses
    curses.cbreak()             # React to keys instantly
    stdscr.keypad(True)         # Enable special keys
    curses.use_env(False)       # Disable environment size checking
    
    # Setup colors
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)    # Snake head
    curses.init_pair(2, curses.COLOR_CYAN, -1)     # Snake body
    curses.init_pair(3, curses.COLOR_RED, -1)      # Food
    curses.init_pair(4, curses.COLOR_WHITE, -1)    # Border
    curses.init_pair(5, curses.COLOR_YELLOW, -1)   # Score

def run_game(stdscr, max_y, max_x, play_height, play_width, high_score=0):
    """Run a complete game session and return the score achieved."""
    # Game state initialization
    score = 0
    game_speed = 100
    game_win = curses.newwin(play_height + 2, play_width + 2, 0, 0)
    game_win.keypad(True)
    game_win.timeout(game_speed)
    
    # Initialize snake and food
    snake = deque([(play_height // 2, play_width // 4)])
    direction = curses.KEY_RIGHT
    food = new_food(snake, play_height, play_width)
    
    # Initial draw
    draw_screen(stdscr, game_win, snake, food, score, high_score, max_x)
    
    # Game loop
    while True:
        # Process input
        key = game_win.getch()
        
        # Handle exit
        if key == ord('q') or key == 27:  # 'q' or ESC
            cleanup()
            return score
            
        # Process direction change
        new_dir = process_input(key, direction)
        if new_dir:
            direction = new_dir
            
        # Calculate new head position
        head_y, head_x = snake[0]
        new_head = move_head(head_y, head_x, direction)
        
        # Check for collision
        if is_collision(new_head, snake, play_height, play_width):
            break
            
        # Update snake position
        snake.appendleft(new_head)
        
        # Handle food
        if new_head == food:
            score += 10
            if game_speed > 50:
                game_speed = max(50, game_speed - 3)
                game_win.timeout(game_speed)
            food = new_food(snake, play_height, play_width)
        else:
            snake.pop()
        
        # Redraw screen
        draw_screen(stdscr, game_win, snake, food, score, high_score, max_x)
    
    return score

def draw_screen(stdscr, game_win, snake, food, score, high_score, max_x):
    """Draw all game elements in a single refresh cycle."""
    # Clear screens
    game_win.erase()
    
    # Draw border with title
    draw_border(game_win)
    
    # Draw food
    try:
        game_win.addch(food[0] + 1, food[1] + 1, ord('*'), curses.color_pair(3) | curses.A_BOLD)
    except curses.error:
        pass
        
    # Draw snake
    draw_snake(game_win, snake)
    
    # Draw score
    draw_score(stdscr, score, high_score, max_x)
    
    # Update screen with double buffering
    stdscr.noutrefresh()
    game_win.noutrefresh()
    curses.doupdate()

def draw_border(win):
    """Draw the border with title."""
    win.box()
    title = "SNAKE GAME"
    width = win.getmaxyx()[1]
    if width > len(title) + 4:
        win.addstr(0, (width - len(title)) // 2, title, curses.A_BOLD | curses.color_pair(5))

def draw_snake(win, snake):
    """Draw the snake."""
    try:
        # Head
        y, x = snake[0]
        win.addch(y + 1, x + 1, ord('O'), curses.color_pair(1) | curses.A_BOLD)
        
        # Body
        for y, x in list(snake)[1:]:
            win.addch(y + 1, x + 1, ord('o'), curses.color_pair(2))
    except curses.error:
        pass

def draw_score(stdscr, score, high_score, max_x):
    """Draw scores at the top."""
    score_text = f" Score: {score} "
    high_score_text = f" High Score: {high_score} "
    
    stdscr.addstr(0, 0, " " * max_x)
    stdscr.addstr(0, 2, score_text, curses.color_pair(5) | curses.A_BOLD)
    stdscr.addstr(0, max_x - len(high_score_text) - 2, high_score_text, curses.color_pair(5) | curses.A_BOLD)

def process_input(key, current_direction):
    """Process keyboard input for direction changes."""
    if key in [curses.KEY_UP, ord('w'), ord('W')] and current_direction != curses.KEY_DOWN:
        return curses.KEY_UP
    elif key in [curses.KEY_DOWN, ord('s'), ord('S')] and current_direction != curses.KEY_UP:
        return curses.KEY_DOWN
    elif key in [curses.KEY_LEFT, ord('a'), ord('A')] and current_direction != curses.KEY_RIGHT:
        return curses.KEY_LEFT
    elif key in [curses.KEY_RIGHT, ord('d'), ord('D')] and current_direction != curses.KEY_LEFT:
        return curses.KEY_RIGHT
    return None

def move_head(y, x, direction):
    """Calculate new head position based on direction."""
    if direction == curses.KEY_UP:
        return (y - 1, x)
    elif direction == curses.KEY_DOWN:
        return (y + 1, x)
    elif direction == curses.KEY_LEFT:
        return (y, x - 1)
    elif direction == curses.KEY_RIGHT:
        return (y, x + 1)

def is_collision(head, snake, height, width):
    """Check if head collides with walls or snake body."""
    y, x = head
    # Wall collision
    if y < 0 or y >= height or x < 0 or x >= width:
        return True
    # Self collision (skip first element which is the current head)
    if head in list(snake)[1:]:
        return True
    return False

def new_food(snake, height, width):
    """Generate a new food position that doesn't overlap with the snake."""
    while True:
        food_y = random.randint(0, height - 1)
        food_x = random.randint(0, width - 1)
        if (food_y, food_x) not in snake:
            return (food_y, food_x)

def show_game_over(stdscr, score, high_score, max_y, max_x):
    """Show game over screen and return True if player wants to quit."""
    stdscr.clear()
    
    center_y = max_y // 2
    
    # Display text
    texts = [
        ("GAME OVER", -3, curses.A_BOLD | curses.color_pair(3)),
        (f"Your Score: {score}", -1, curses.color_pair(5)),
        (f"High Score: {high_score}", 0, curses.color_pair(5)),
        ("Press 'r' to restart", 2, 0),
        ("Press 'q' to quit", 3, 0)
    ]
    
    for text, y_offset, attr in texts:
        stdscr.addstr(center_y + y_offset, max_x // 2 - len(text) // 2, text, attr)
    
    # Use double buffering
    stdscr.noutrefresh()
    curses.doupdate()
    
    # Get user choice
    stdscr.nodelay(False)  # Switch to blocking mode
    while True:
        key = stdscr.getch()
        if key == ord('q'):
            return True
        elif key == ord('r'):
            return False

def cleanup():
    """Clean up terminal state before exiting."""
    if _stdscr is not None:
        try:
            curses.endwin()
            print("\033[?25l\033[2J\033[H", end="")
            
            # Center goodbye message at top
            try:
                rows, cols = _stdscr.getmaxyx()
            except:
                rows, cols = 24, 80
                
            goodbye_msg = "Thanks for playing Snake!"
            print("\033[2;{}H{}".format((cols - len(goodbye_msg)) // 2, goodbye_msg))
            print("\033[3;{}H{}".format((cols - len("Goodbye!")) // 2, "Goodbye!"))
            
            sys.stdout.flush()
        except Exception:
            pass

def handle_exit(sig, frame):
    """Handle termination signals."""
    cleanup()
    sys.exit(0)

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()