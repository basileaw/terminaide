#!/usr/bin/env python3
# tests/client_2.py

"""
Sample terminal client for terminaide multi-script testing.
This client implements a simple ASCII art snake game.
"""

import os
import sys
import time
import random
import threading
from typing import List, Tuple, Dict, Set
import readchar

# ASCII art title
TITLE = """
╔════════════════════════════════════════╗
║               ASCII SNAKE              ║
║         Use WASD keys to move          ║
║           Press Q to quit              ║
╚════════════════════════════════════════╝
"""

# Game configuration
WIDTH = 30
HEIGHT = 15
SNAKE_CHAR = '■'
FOOD_CHAR = '●'
WALL_CHAR = '█'
EMPTY_CHAR = ' '

# Direction definitions
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)

# Map keys to directions
KEY_MAP = {
    'w': UP,
    'a': LEFT,
    's': DOWN,
    'd': RIGHT,
    'W': UP,
    'A': LEFT,
    'S': DOWN,
    'D': RIGHT
}

class SnakeGame:
    def __init__(self, width: int = WIDTH, height: int = HEIGHT):
        self.width = width
        self.height = height
        self.score = 0
        self.running = False
        self.game_over = False
        self.direction = RIGHT
        self.next_direction = RIGHT
        self.snake: List[Tuple[int, int]] = []
        self.food: Tuple[int, int] = (0, 0)
        
    def setup(self) -> None:
        """Initialize the game state."""
        self.score = 0
        self.game_over = False
        self.direction = RIGHT
        self.next_direction = RIGHT
        
        # Initialize snake in the middle of the board
        x, y = self.width // 2, self.height // 2
        self.snake = [(x, y), (x-1, y), (x-2, y)]
        
        # Place initial food
        self.place_food()
        
    def place_food(self) -> None:
        """Place food in a random empty cell."""
        occupied = set(self.snake)
        
        # Find all empty cells
        empty_cells = [
            (x, y) for x in range(1, self.width-1)
                   for y in range(1, self.height-1)
                   if (x, y) not in occupied
        ]
        
        if empty_cells:
            self.food = random.choice(empty_cells)
        else:
            # No empty cells left, player wins!
            self.game_over = True
            
    def change_direction(self, new_dir: Tuple[int, int]) -> None:
        """Change snake direction but prevent 180-degree turns."""
        # Skip if we're trying to go in the opposite direction
        if (self.direction[0] + new_dir[0] == 0 and 
            self.direction[1] + new_dir[1] == 0):
            return
            
        self.next_direction = new_dir
        
    def move(self) -> None:
        """Move the snake in the current direction."""
        if self.game_over:
            return
            
        # Update direction
        self.direction = self.next_direction
        
        # Calculate new head position
        head_x, head_y = self.snake[0]
        dx, dy = self.direction
        new_head = (head_x + dx, head_y + dy)
        
        # Check for collisions
        if (new_head[0] <= 0 or new_head[0] >= self.width - 1 or
            new_head[1] <= 0 or new_head[1] >= self.height - 1 or
            new_head in self.snake):
            self.game_over = True
            return
            
        # Check if food was eaten
        if new_head == self.food:
            self.score += 10
            self.snake.insert(0, new_head)
            self.place_food()
        else:
            # Move snake (add new head, remove tail)
            self.snake.insert(0, new_head)
            self.snake.pop()
            
    def draw(self) -> str:
        """Render the game state to a string."""
        # Create empty board
        board = [[EMPTY_CHAR for _ in range(self.width)] 
                for _ in range(self.height)]
        
        # Draw walls
        for x in range(self.width):
            board[0][x] = WALL_CHAR
            board[self.height-1][x] = WALL_CHAR
        for y in range(self.height):
            board[y][0] = WALL_CHAR
            board[y][self.width-1] = WALL_CHAR
        
        # Draw snake
        for segment in self.snake:
            x, y = segment
            if 0 <= x < self.width and 0 <= y < self.height:
                board[y][x] = SNAKE_CHAR
        
        # Draw food
        fx, fy = self.food
        board[fy][fx] = FOOD_CHAR
        
        # Convert board to string
        rows = [''.join(row) for row in board]
        
        # Add score
        game_str = f"\nScore: {self.score}\n\n"
        game_str += '\n'.join(rows)
        
        if self.game_over:
            game_str += "\n\nGame Over! Press R to restart or Q to quit."
            
        return game_str

def clear_screen() -> None:
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def main() -> None:
    """Main function to run the snake game."""
    game = SnakeGame()
    game.setup()
    
    # Game settings
    tick_rate = 0.2  # seconds per tick
    
    # Display initial state
    clear_screen()
    print(TITLE)
    print(game.draw())
    
    # Start the game
    game.running = True
    
    # Main game loop
    last_tick = time.time()
    
    try:
        while game.running:
            # Non-blocking input
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                key = sys.stdin.read(1)
                
                if key == 'q':
                    game.running = False
                elif key == 'r' and game.game_over:
                    game.setup()
                elif key in KEY_MAP:
                    game.change_direction(KEY_MAP[key])
            
            # Game tick
            current_time = time.time()
            if current_time - last_tick >= tick_rate:
                game.move()
                clear_screen()
                print(TITLE)
                print(game.draw())
                last_tick = current_time
                
            # Small sleep to prevent CPU hogging
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        pass
        
    print("\nThanks for playing ASCII Snake!")

# Alternative implementation that works better in terminal integration
def terminal_main():
    """Main function adapted for terminal integration."""
    game = SnakeGame()
    game.setup()
    
    # Game settings
    tick_rate = 0.2  # seconds per tick
    
    def input_thread():
        """Thread to handle keyboard input."""
        while game.running:
            key = readchar.readkey()
            
            if key == 'q':
                game.running = False
            elif key == 'r' and game.game_over:
                game.setup()
            elif key in KEY_MAP:
                game.change_direction(KEY_MAP[key])
                
    # Start input thread
    input_handler = threading.Thread(target=input_thread)
    input_handler.daemon = True
    input_handler.start()
    
    # Display initial state
    clear_screen()
    print(TITLE)
    print(game.draw())
    
    # Start the game
    game.running = True
    
    # Main game loop
    while game.running:
        time.sleep(tick_rate)
        game.move()
        clear_screen()
        print(TITLE)
        print(game.draw())
    
    print("\nThanks for playing ASCII Snake!")

if __name__ == "__main__":
    try:
        # Check if we have access to select module
        import select
        main()
    except (ImportError, AttributeError):
        # Fallback to the terminal-friendly version
        # Note: This requires the 'readchar' package
        try:
            import readchar
            terminal_main()
        except ImportError:
            print("This game requires either the 'select' module or the 'readchar' package.")
            print("Try: pip install readchar")
            sys.exit(1)