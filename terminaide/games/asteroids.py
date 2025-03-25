# terminaide/games/asteroids.py

import curses
import math
import random
import time
import signal
import sys

# Globals to mirror snake.py
stdscr = None
exit_requested = False
back_to_menu = False

# ASCII art to display at the top of the screen (centered).
ASTEROIDS_ASCII_ART = [
    "████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗       █████╗ ███████╗████████╗███████╗██████╗  ██████╗ ██╗██████╗ ███████╗",
    "╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║      ██╔══██╗██╔════╝╚══██╔══╝██╔════╝██╔══██╗██╔═══██╗██║██╔══██╗██╔════╝",
    "   ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║█████╗███████║███████╗   ██║   █████╗  ██████╔╝██║   ██║██║██║  ██║███████╗",
    "   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║╚════╝██╔══██║╚════██║   ██║   ██╔══╝  ██╔══██╗██║   ██║██║██║  ██║╚════██║",
    "   ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║      ██║  ██║███████║   ██║   ███████╗██║  ██║╚██████╔╝██║██████╔╝███████║",
    "   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝      ╚═╝  ╚═╝╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝╚═════╝ ╚══════╝",
]

# Colors to match snake's aesthetic
# (1 = green, 2 = cyan, 3 = red, 4 = white, 5 = yellow)
SHIP_COLOR_PAIR = 1
BULLET_COLOR_PAIR = 2
ASTEROID_COLOR_PAIR = 3
TEXT_COLOR_PAIR = 5  # for scoreboard, messages, etc.

# Game constants
MAX_ASTEROIDS = 5
BULLET_SPEED = 1.5
SHIP_ACCELERATION = 0.1
ROTATION_SPEED = 10  # degrees per key press
ASTEROID_MIN_SPEED = 0.03
ASTEROID_MAX_SPEED = 0.15

# We can pick from multiple asteroid symbols
ASTEROID_SYMBOLS = ["O", "@", "0", "#"]

# For quick direction-based ship display
SHIP_SYMBOL_UP = "^"   
SHIP_SYMBOL_RIGHT = ">"
SHIP_SYMBOL_DOWN = "v"
SHIP_SYMBOL_LEFT = "<"

BULLET_SYMBOL = "*"

# How fast the game updates in seconds
TICK_RATE = 0.03

def handle_exit(sig, frame):
    """
    Handle Ctrl+C (SIGINT) to gracefully exit.
    """
    global exit_requested
    exit_requested = True

def cleanup():
    """
    Clean up terminal state when exiting, matching the style of snake.py.
    """
    global stdscr
    if stdscr:
        try:
            curses.endwin()
            # Clear screen, hide cursor, show farewell messages (like snake.py)
            print("\033[?25l\033[2J\033[H", end="")
            try:
                rows, cols = stdscr.getmaxyx()
            except:
                rows, cols = 24, 80
            msg = "Thanks for playing Asteroids!"
            print("\033[2;{}H{}".format((cols-len(msg))//2, msg))
            print("\033[3;{}H{}".format((cols-len("Goodbye!"))//2, "Goodbye!"))
            sys.stdout.flush()
        except:
            pass

def setup_terminal(stdscr_window):
    """
    Configure curses settings, color pairs, etc., in a manner matching snake.py.
    """
    curses.curs_set(0)
    curses.noecho()
    curses.cbreak()
    stdscr_window.keypad(True)

    # Let curses use the terminal's default size and colors
    curses.use_env(False)
    curses.start_color()
    curses.use_default_colors()

    # Same color pairs as snake
    curses.init_pair(1, curses.COLOR_GREEN, -1)   # e.g. ship
    curses.init_pair(2, curses.COLOR_CYAN, -1)   # e.g. bullets
    curses.init_pair(3, curses.COLOR_RED, -1)    # e.g. asteroids
    curses.init_pair(4, curses.COLOR_WHITE, -1)
    curses.init_pair(5, curses.COLOR_YELLOW, -1) # e.g. score text

def wrap_position(x, y, max_x, max_y):
    """
    Wrap (x, y) around the boundaries, so objects remain on screen.
    """
    new_x = x % max_x
    new_y = y % max_y
    return new_x, new_y

class GameObject:
    """
    Base class for all objects in the game (ship, asteroids, bullets).
    """
    def __init__(self, x, y, vx, vy, symbol, color_pair):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.symbol = symbol
        self.color_pair = color_pair
        self.alive = True

    def update(self, max_x, max_y):
        """
        Update position and wrap around screen edges.
        """
        self.x += self.vx
        self.y += self.vy
        self.x, self.y = wrap_position(self.x, self.y, max_x, max_y)

    def draw(self, screen):
        """
        Draw the object on the curses screen if alive.
        """
        if self.alive:
            try:
                screen.addch(
                    int(self.y),
                    int(self.x),
                    self.symbol,
                    curses.color_pair(self.color_pair)
                )
            except:
                pass  # if out of bounds for some reason

class Ship(GameObject):
    """
    Player's ship. Has an orientation angle and can accelerate in direction faced.
    """
    def __init__(self, x, y):
        super().__init__(x, y, 0, 0, SHIP_SYMBOL_UP, SHIP_COLOR_PAIR)
        self.angle = 0  # in degrees

    def rotate_left(self):
        self.angle = (self.angle - ROTATION_SPEED) % 360

    def rotate_right(self):
        self.angle = (self.angle + ROTATION_SPEED) % 360

    def accelerate(self):
        rad = math.radians(self.angle)
        self.vx += math.cos(rad) * SHIP_ACCELERATION
        self.vy += math.sin(rad) * SHIP_ACCELERATION

    def shoot(self):
        rad = math.radians(self.angle)
        bullet_vx = self.vx + math.cos(rad) * BULLET_SPEED
        bullet_vy = self.vy + math.sin(rad) * BULLET_SPEED
        return Bullet(self.x, self.y, bullet_vx, bullet_vy, BULLET_SYMBOL, BULLET_COLOR_PAIR)

    def draw(self, screen):
        """
        Draw the ship with an ASCII character for orientation.
        We'll pick the closest of 0,90,180,270 degrees for display.
        """
        if not self.alive:
            return
        direction_map = [
            (0,   SHIP_SYMBOL_UP),
            (90,  SHIP_SYMBOL_RIGHT),
            (180, SHIP_SYMBOL_DOWN),
            (270, SHIP_SYMBOL_LEFT)
        ]
        # Find the best match for self.angle
        diffs = [
            (abs(((deg - self.angle) + 180) % 360 - 180), sym)
            for (deg, sym) in direction_map
        ]
        diffs.sort(key=lambda x: x[0])
        self.symbol = diffs[0][1]
        super().draw(screen)

class Asteroid(GameObject):
    """
    Represents an asteroid with random velocity, position, and symbol.
    """
    pass

class Bullet(GameObject):
    """
    Represents a bullet shot by the ship.
    """
    def update(self, max_x, max_y):
        super().update(max_x, max_y)

def check_collision(obj1, obj2):
    """
    Simple collision check based on distance between centers.
    """
    distance = math.hypot(obj1.x - obj2.x, obj1.y - obj2.y)
    return distance < 1.0

def show_game_over(stdscr, score, high_score, max_y, max_x):
    """
    Display a 'Game Over' screen (similar to snake),
    then wait for the user to press 'r' or 'q'.
    
    Returns True if user quits, False if user restarts.
    """
    stdscr.clear()
    cy = max_y // 2
    
    lines = [
        ("GAME OVER", -3, curses.A_BOLD | curses.color_pair(3)),
        (f"Your Score: {score}", -1, curses.color_pair(TEXT_COLOR_PAIR)),
        (f"High Score: {high_score}", 0, curses.color_pair(TEXT_COLOR_PAIR)),
        ("Press 'r' to restart", 2, 0),
        ("Press 'q' to quit", 3, 0),
    ]
    for txt, offset, attr in lines:
        stdscr.addstr(cy + offset, max_x // 2 - len(txt)//2, txt, attr)
    
    stdscr.noutrefresh()
    curses.doupdate()
    stdscr.nodelay(False)
    
    while True:
        key = stdscr.getch()
        if key == ord('q'):
            return True
        if key == ord('r'):
            return False

def draw_score(stdscr, score, high_score, start_y, max_x):
    """
    Draw the scoreboard at `start_y`, matching style of snake.py (Score / High Score).
    """
    # Clear the line if you want, or partially clear. We'll just write directly.
    stdscr.addstr(start_y, 0, " " * max_x)
    stdscr.addstr(start_y, 2, f" Score: {score} ", curses.color_pair(TEXT_COLOR_PAIR) | curses.A_BOLD)
    txt = f" High Score: {high_score} "
    stdscr.addstr(start_y, max_x - len(txt) - 2, txt, curses.color_pair(TEXT_COLOR_PAIR) | curses.A_BOLD)

def draw_title(stdscr, max_x):
    """
    Draw the ASCII art (ASTEROIDS_ASCII_ART) at the top of the screen, each line centered.
    Returns the number of lines used (so we know where to put the scoreboard).
    """
    for i, line in enumerate(ASTEROIDS_ASCII_ART):
        x_pos = max(0, (max_x // 2) - (len(line) // 2))
        stdscr.addstr(i, x_pos, line, curses.color_pair(TEXT_COLOR_PAIR) | curses.A_BOLD)
    return len(ASTEROIDS_ASCII_ART)

def run_game(stdscr, max_y, max_x, high_score):
    """
    One round of the Asteroids game.  
    Returns the final score for this round.
    """
    global exit_requested, back_to_menu

    # Create player ship in the center
    ship = Ship(max_x // 2, max_y // 2)

    # Create asteroids
    asteroids = []
    for _ in range(MAX_ASTEROIDS):
        x = random.randint(0, max_x - 1)
        y = random.randint(0, max_y - 1)
        vx = random.uniform(ASTEROID_MIN_SPEED, ASTEROID_MAX_SPEED) * random.choice([-1, 1])
        vy = random.uniform(ASTEROID_MIN_SPEED, ASTEROID_MAX_SPEED) * random.choice([-1, 1])
        symbol = random.choice(ASTEROID_SYMBOLS)
        asteroids.append(Asteroid(x, y, vx, vy, symbol, ASTEROID_COLOR_PAIR))

    bullets = []
    score = 0

    # Non-blocking input
    stdscr.nodelay(True)
    stdscr.timeout(0)

    while True:
        if exit_requested:
            return score

        # Check user input
        try:
            key = stdscr.getch()
        except:
            key = -1

        if key != -1:
            # 'q' => exit, ESC => exit
            if key in (ord('q'), 27):
                exit_requested = True
                return score
            
            # If from the index menu, pressing backspace or delete => return to menu
            if key in (curses.KEY_BACKSPACE, 8, 127, curses.KEY_DC, 330):
                back_to_menu = True
                exit_requested = True
                return score

            if key == curses.KEY_LEFT:
                ship.rotate_left()
            elif key == curses.KEY_RIGHT:
                ship.rotate_right()
            elif key == curses.KEY_UP:
                ship.accelerate()
            elif key == ord(' '):
                bullets.append(ship.shoot())

        # Update objects
        ship.update(max_x, max_y)
        for asteroid in asteroids:
            asteroid.update(max_x, max_y)
        for bullet in bullets:
            bullet.update(max_x, max_y)

        # Check collisions
        for asteroid in asteroids:
            if asteroid.alive and ship.alive and check_collision(ship, asteroid):
                # Ship hits an asteroid -> ship is destroyed => game ends
                ship.alive = False

            for bullet in bullets:
                if bullet.alive and asteroid.alive:
                    if check_collision(bullet, asteroid):
                        bullet.alive = False
                        asteroid.alive = False
                        score += 50  # Give some points for destroying an asteroid

        # Remove dead objects
        asteroids = [a for a in asteroids if a.alive]
        bullets = [b for b in bullets if b.alive]

        # Clear screen and draw ASCII art + scoreboard
        stdscr.clear()
        title_height = draw_title(stdscr, max_x)
        # scoreboard just below the ASCII art
        draw_score(stdscr, score, high_score, title_height, max_x)

        # If ship is alive, draw it
        if ship.alive:
            ship.draw(stdscr)

        # Draw asteroids & bullets
        for asteroid in asteroids:
            asteroid.draw(stdscr)
        for bullet in bullets:
            bullet.draw(stdscr)

        stdscr.refresh()

        # End condition if ship is not alive
        if not ship.alive:
            break

        # If all asteroids are destroyed, respawn them
        if len(asteroids) == 0:
            for _ in range(MAX_ASTEROIDS):
                x = random.randint(0, max_x - 1)
                y = random.randint(0, max_y - 1)
                vx = random.uniform(ASTEROID_MIN_SPEED, ASTEROID_MAX_SPEED) * random.choice([-1, 1])
                vy = random.uniform(ASTEROID_MIN_SPEED, ASTEROID_MAX_SPEED) * random.choice([-1, 1])
                symbol = random.choice(ASTEROID_SYMBOLS)
                asteroids.append(Asteroid(x, y, vx, vy, symbol, ASTEROID_COLOR_PAIR))

        # Control the game speed
        time.sleep(TICK_RATE)

    return score

def _asteroids_game_loop(stdscr_param, from_index=False):
    """
    Main Asteroids loop (similar to _snake_game_loop).
    Allows multiple rounds (restart) until user quits.
    
    If 'back_to_menu' and from_index is True, return "back_to_menu".
    Otherwise, return None.
    """
    global stdscr, exit_requested, back_to_menu
    stdscr = stdscr_param
    exit_requested = False
    back_to_menu = False

    signal.signal(signal.SIGINT, handle_exit)
    setup_terminal(stdscr)
    
    max_y, max_x = stdscr.getmaxyx()
    # Minimal boundary
    max_x = max(10, max_x)
    max_y = max(10, max_y)

    high_score = 0

    while True:
        if exit_requested:
            # Check if we're returning to the menu or fully exiting
            if back_to_menu and from_index:
                cleanup()
                return "back_to_menu"
            else:
                cleanup()
                return None

        # Play one round
        score = run_game(stdscr, max_y, max_x, high_score)
        if exit_requested:
            # Possibly returning to menu or exiting
            if back_to_menu and from_index:
                cleanup()
                return "back_to_menu"
            else:
                cleanup()
                return None

        # Update high score
        if score > high_score:
            high_score = score
        
        # Show game over, see if user restarts or quits
        quit_game = show_game_over(stdscr, score, high_score, max_y, max_x)
        if quit_game:
            break  # user pressed 'q'
        # else they pressed 'r' => loop again

    return None

def play_asteroids(from_index=False):
    """
    Public-facing function to launch Asteroids, similar to snake's play_snake().
    If 'from_index' is True, backspace/delete will return "back_to_menu" instead of fully exiting.
    """
    try:
        result = curses.wrapper(lambda stdscr_param: _asteroids_game_loop(stdscr_param, from_index))
        return result
    except Exception as e:
        print(f"\n\033[31mError in asteroids game: {e}\033[0m")
    finally:
        cleanup()

# If launched directly:
if __name__ == "__main__":
    print("\033[?25l\033[2J\033[H", end="")
    try:
        play_asteroids()
    finally:
        cleanup()
