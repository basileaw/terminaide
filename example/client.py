# Global reference to store stdscr for cleanup
_stdscr = None

def cleanup():
    """Clean up the terminal state before exiting."""
    # make cursor invisible 
    print("\033[?25l", end="")
    
    if _stdscr is not None:
        try:
            # End curses mode
            curses.endwin()
            # Clear screen using ANSI escape sequence
            print("\033[2J\033[H", end="")
            
            # Get terminal dimensions (if possible)
            try:
                rows, cols = _stdscr.getmaxyx()
            except:
                rows, cols = 24, 80  # Default fallback
                
            # Center goodbye message at the top
            goodbye_msg = "Thanks for playing Snake!"
            print("\033[2;{}H{}".format((cols - len(goodbye_msg)) // 2, goodbye_msg))
            print("\033[3;{}H{}".format((cols - len("Goodbye!")) // 2, "Goodbye!"))
            
            sys.stdout.flush()
        except Exception:
            pass  # Fail silently if cleanup has issues

def handle_exit(sig, frame):
    """Handle SIGINT (Ctrl+C) and other termination signals."""
    cleanup()
    print("Game terminated. Goodbye!")
    sys.exit(0)# terminal_snake.py

import curses
import random
import time
import signal
import sys
from collections import deque

def main(stdscr):
    # Global reference to stdscr for cleanup
    global _stdscr
    _stdscr = stdscr
    
    # Setup signal handlers for graceful exit
    signal.signal(signal.SIGINT, handle_exit)
    
    # Setup terminal
    curses.curs_set(0)           # Hide cursor
    curses.noecho()              # Don't echo keypresses
    curses.cbreak()              # React to keys instantly without buffer
    stdscr.keypad(True)          # Enable special keys
    
    # Set up colors
    curses.start_color()
    curses.use_default_colors()  # Use terminal's default colors
    curses.init_pair(1, curses.COLOR_GREEN, -1)     # Snake head
    curses.init_pair(2, curses.COLOR_CYAN, -1)      # Snake body
    curses.init_pair(3, curses.COLOR_RED, -1)       # Food
    curses.init_pair(4, curses.COLOR_WHITE, -1)     # Border
    curses.init_pair(5, curses.COLOR_YELLOW, -1)    # Score
    
    # Get usable screen dimensions (avoiding bottom-right corner)
    max_y, max_x = stdscr.getmaxyx()
    play_height, play_width = max_y - 2, max_x - 2  # Leave border space
    
    # Main game loop with restart capability
    should_quit = False
    high_score = 0  # Track high score across games
    while not should_quit:
        current_score = run_game(stdscr, max_y, max_x, play_height, play_width, high_score)
        high_score = max(high_score, current_score)
        should_quit = show_game_over_with_restart(stdscr, current_score, high_score, max_y, max_x)

def run_game(stdscr, max_y, max_x, play_height, play_width, high_score=0):
    """Run a complete game session with ability to restart. Returns the score achieved."""
    # Setup for double buffering to eliminate flicker
    curses.use_env(False)  # Disable environment size checking
    
    # Game state
    score = 0
    game_over = False
    game_speed = 100             # Track current game speed
    
    # Create game window with border
    game_win = curses.newwin(play_height + 2, play_width + 2, 0, 0)
    game_win.keypad(True)        # Enable special keys in the window
    game_win.timeout(game_speed) # Set input timeout
    
    # Initialize snake as a deque for efficient append/pop operations
    snake = deque([(play_height // 2, play_width // 4)])
    direction = curses.KEY_RIGHT
    
    # Initialize food position
    food = new_food_position(snake, play_height, play_width)
    
    # Initial draw
    stdscr.clear()
    game_win.clear()
    draw_border(game_win)
    draw_score(stdscr, score, high_score, max_x)
    
    # Initial screen update using double buffering
    stdscr.noutrefresh()
    game_win.noutrefresh()
    curses.doupdate()  # Update the physical screen all at once
    
    # Game loop
    while not game_over:
        # Get user input with timeout
        key = game_win.getch()
        
        # Process direction change
        new_direction = process_input(key, direction)
        if new_direction:
            direction = new_direction
        
        # Handle quit key
        if key == ord('q'):
            return True  # Signal to quit completely
            
        # Calculate new head position
        head_y, head_x = snake[0]
        new_head = move_snake_head(head_y, head_x, direction)
        
        # Check for collisions
        if (is_collision(new_head, snake, play_height, play_width)):
            game_over = True
            continue
            
        # Add new head
        snake.appendleft(new_head)
        
        # Check for food
        if new_head == food:
            # Increase score and speed up the game slightly
            score += 10
            if game_speed > 50:  # Don't go faster than 50ms
                game_speed = max(50, game_speed - 3)
                game_win.timeout(game_speed)
            
            # Generate new food
            food = new_food_position(snake, play_height, play_width)
        else:
            # Remove tail if no food was eaten
            snake.pop()
        
        # Completely redraw game window
        game_win.erase()  # Erase everything first
        draw_border(game_win)  # Redraw border
        
        # Draw food
        try:
            game_win.addch(food[0] + 1, food[1] + 1, 'F', curses.color_pair(3) | curses.A_BOLD)
        except curses.error:
            pass
            
        # Draw snake
        draw_snake(game_win, snake)
        
        # Update score
        draw_score(stdscr, score, high_score, max_x)
        
        # Use double buffering to avoid flicker
        stdscr.noutrefresh()
        game_win.noutrefresh()
        curses.doupdate()  # Update physical screen all at once
    
    # Game over
    return score  # Return score to update high score

def new_food_position(snake, height, width):
    """Generate a new food position that doesn't overlap with the snake."""
    while True:
        food_y = random.randint(0, height - 1)
        food_x = random.randint(0, width - 1)
        if (food_y, food_x) not in snake:
            return (food_y, food_x)

def process_input(key, current_direction):
    """Process keyboard input and return the new direction if valid."""
    if key in [curses.KEY_UP, ord('w'), ord('W')] and current_direction != curses.KEY_DOWN:
        return curses.KEY_UP
    elif key in [curses.KEY_DOWN, ord('s'), ord('S')] and current_direction != curses.KEY_UP:
        return curses.KEY_DOWN
    elif key in [curses.KEY_LEFT, ord('a'), ord('A')] and current_direction != curses.KEY_RIGHT:
        return curses.KEY_LEFT
    elif key in [curses.KEY_RIGHT, ord('d'), ord('D')] and current_direction != curses.KEY_LEFT:
        return curses.KEY_RIGHT
    # Add escape key handling
    elif key == 27:  # ESC key
        cleanup()
        sys.exit(0)
    return None

def move_snake_head(y, x, direction):
    """Calculate the new head position based on the current direction."""
    if direction == curses.KEY_UP:
        return (y - 1, x)
    elif direction == curses.KEY_DOWN:
        return (y + 1, x)
    elif direction == curses.KEY_LEFT:
        return (y, x - 1)
    elif direction == curses.KEY_RIGHT:
        return (y, x + 1)

def is_collision(head, snake, height, width):
    """Check if the new head position collides with walls or snake body."""
    head_y, head_x = head
    # Check wall collision
    if head_y < 0 or head_y >= height or head_x < 0 or head_x >= width:
        return True
    # Check self collision (skip the first element which is the current head)
    if head in list(snake)[1:]:
        return True
    return False

def draw_border(win):
    """Draw the game border with title."""
    win.box()
    
    # Add title in the top border
    title = "IT'S SNAKE, BABY!!!"
    width = win.getmaxyx()[1]
    if width > len(title) + 4:  # Make sure we have enough room
        win.addstr(0, (width - len(title)) // 2, title, curses.A_BOLD | curses.color_pair(5))
    
    # No refresh - we'll do it all at once

def draw_snake(win, snake):
    """Draw the snake with different colors for head and body."""
    # Clear previous head position (in case it's now a body segment)
    try:
        # Get the head position
        head_y, head_x = snake[0]
        
        # Draw head with special character
        win.addch(head_y + 1, head_x + 1, '@', curses.color_pair(1) | curses.A_BOLD)
        
        # Draw body segments with distinct characters and colors
        for i, (y, x) in enumerate(list(snake)[1:], 1):
            # Use alternating characters for body segments
            char = 'O' if i % 2 == 0 else '0'
            win.addch(y + 1, x + 1, char, curses.color_pair(2))
    except curses.error:
        # Safely handle bottom-right corner case
        pass

def draw_score(stdscr, score, high_score, max_x):
    """Draw the score at the top of the screen."""
    score_text = f" Score: {score} "
    high_score_text = f" High Score: {high_score} "
    
    # Clear the score area first
    stdscr.addstr(0, 0, " " * max_x)
    
    # Draw current score on left side
    stdscr.addstr(0, 2, score_text, curses.color_pair(5) | curses.A_BOLD)
    
    # Draw high score on right side
    stdscr.addstr(0, max_x - len(high_score_text) - 2, high_score_text, curses.color_pair(5) | curses.A_BOLD)
    
    # No refresh - we'll do it all at once

def show_game_over_with_restart(stdscr, score, high_score, max_y, max_x):
    """Show the game over screen with restart option. Returns True if player wants to quit."""
    stdscr.clear()
    
    # Game over text
    game_over_text = "GAME OVER"
    score_text = f"Your Score: {score}"
    high_score_text = f"High Score: {high_score}"
    restart_text = "Press 'r' to restart"
    quit_text = "Press 'q' to quit"
    
    # Calculate center positions
    center_y = max_y // 2
    
    # Display text
    stdscr.addstr(center_y - 3, max_x // 2 - len(game_over_text) // 2, game_over_text, curses.A_BOLD | curses.color_pair(3))
    stdscr.addstr(center_y - 1, max_x // 2 - len(score_text) // 2, score_text, curses.color_pair(5))
    stdscr.addstr(center_y, max_x // 2 - len(high_score_text) // 2, high_score_text, curses.color_pair(5))
    stdscr.addstr(center_y + 2, max_x // 2 - len(restart_text) // 2, restart_text)
    stdscr.addstr(center_y + 3, max_x // 2 - len(quit_text) // 2, quit_text)
    
    # Use double buffering
    stdscr.noutrefresh()
    curses.doupdate()
    
    # Wait for user input - r to restart, q to quit
    stdscr.nodelay(False)  # Switch to blocking mode
    while True:
        key = stdscr.getch()
        if key == ord('q'):
            return True  # Signal to quit
        elif key == ord('r'):
            return False  # Signal to restart
    
    stdscr.refresh()
    
    # Wait for user input - r to restart, q to quit
    stdscr.nodelay(False)  # Switch to blocking mode
    while True:
        key = stdscr.getch()
        if key == ord('q'):
            return True  # Signal to quit
        elif key == ord('r'):
            return False  # Signal to restart


if __name__ == "__main__":
    try:
        # Start the game
        curses.wrapper(main)
    except KeyboardInterrupt:
        # Handle Ctrl+C outside of curses (though our signal handler should catch it)
        pass
    finally:
        # Ensure cleanup happens no matter how we exit
        cleanup()