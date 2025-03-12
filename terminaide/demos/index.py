# terminaide/demos/index.py

import curses, signal, sys
import importlib

_stdscr = None
_exit_requested = False

def handle_exit(sig, frame):
    """Handle SIGINT (Ctrl+C) for clean program exit."""
    global _exit_requested
    _exit_requested = True

def cleanup():
    """Restore terminal state and print goodbye message."""
    if _stdscr:
        try:
            curses.endwin()
            print("\033[?25l\033[2J\033[H", end="")
            try:
                rows, cols = _stdscr.getmaxyx()
            except:
                rows, cols = 24, 80
            msg = "Thank you for using terminaide"
            print("\033[2;{}H{}".format((cols-len(msg))//2, msg))
            print("\033[3;{}H{}".format((cols-len("Goodbye!"))//2, "Goodbye!"))
            sys.stdout.flush()
        except:
            pass

def safe_addstr(stdscr, y, x, text, attr=0):
    """Safely add a string to the screen, handling boundary conditions."""
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

def draw_horizontal_line(stdscr, y, x, width, attr=0):
    """Draw a horizontal line on the screen."""
    for i in range(width):
        safe_addstr(stdscr, y, x+i, " ", attr)

def index_menu(stdscr):
    """Main menu interface."""
    global _stdscr, _exit_requested
    _stdscr = stdscr
    _exit_requested = False
    
    # Set up signal handler for SIGINT (Ctrl+C)
    signal.signal(signal.SIGINT, handle_exit)
    
    # Configure terminal
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLUE, -1)
    curses.init_pair(2, curses.COLOR_WHITE, -1)
    curses.init_pair(3, curses.COLOR_CYAN, -1)
    curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(6, curses.COLOR_GREEN, -1)
    
    curses.curs_set(0)  # Hide cursor
    
    # Setup screen
    stdscr.clear()
    options = ["Snake", "Tetris", "Pong"]
    co = 0  # Current option
    po = 0  # Previous option
    
    # Get screen dimensions
    my, mx = stdscr.getmaxyx()
    
    # Title ASCII art options based on screen width
    title_lines = [
        "████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗      █████╗ ██████╗  ██████╗ █████╗ ██████╗ ███████╗",
        "╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║     ██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝",
        "   ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║     ███████║██████╔╝██║     ███████║██║  ██║█████╗  ",
        "   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║     ██╔══██║██╔══██╗██║     ██╔══██║██║  ██║██╔══╝  ",
        "   ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║     ██║  ██║██║  ██║╚██████╗██║  ██║██████╔╝███████╗",
        "   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝     ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═════╝ ╚══════╝"
    ]
    
    simple_title_lines = [
        " _____              _         _                   _      ",
        "|_   _|__ _ __ _ __ (_)_ __   /_\\  _ __ ___ __ _  _| | ___ ",
        "  | |/ _ \\ '__| '_ \\| | '_ \\ //_\\\\| '__/ __/ _` |/ _` |/ _ \\",
        "  | |  __/ |  | | | | | | | /  _ \\ | | (_| (_| | (_| |  __/",
        "  |_|\\___|_|  |_| |_|_|_| |_\\_/ \\_\\_|  \\___\\__,_|\\__,_|\\___|"
    ]
    
    very_simple_title = [
        "==============================",
        "||     TERMIN-ARCADE       ||",
        "=============================="
    ]
    
    # Choose title based on screen width
    if mx >= 90:
        title_to_use = title_lines
    elif mx >= 60:
        title_to_use = simple_title_lines
    else:
        title_to_use = very_simple_title
    
    # Draw title
    for i, line in enumerate(title_to_use):
        if len(line) <= mx:
            safe_addstr(stdscr, 1+i, (mx-len(line))//2, line, curses.color_pair(1)|curses.A_BOLD)
    
    # Draw instructions
    sy = 2 + len(title_to_use)
    instr = "Use ↑/↓ to navigate, Enter to select, Q to quit"
    safe_addstr(stdscr, sy+2, (mx-len(instr))//2, instr, curses.color_pair(2))
    
    # Add backspace/delete instruction
    back_instr = "Press Backspace or Delete in games to return to this menu"
    safe_addstr(stdscr, sy+3, (mx-len(back_instr))//2, back_instr, curses.color_pair(6)|curses.A_BOLD)
    
    # Calculate menu layout
    mol = max(len(o) for o in options)
    oy = sy + 5
    
    # Initial draw of menu options
    for i, o in enumerate(options):
        st = curses.color_pair(5) if i == co else curses.color_pair(4)
        pad = " " * 3
        sp = mol - len(o)
        ls = sp // 2
        rs = sp - ls
        bt = f"{pad}{' ' * ls}{o}{' ' * rs}{pad}"
        safe_addstr(stdscr, oy+i*2, (mx-len(bt))//2, bt, st|curses.A_BOLD)
    
    # Main menu loop
    while True:
        if _exit_requested:
            break
            
        # Update menu selection if changed
        if co != po:
            # Redraw previous selection (unselected)
            st = curses.color_pair(4)|curses.A_BOLD
            sp = mol - len(options[po])
            ls = sp // 2
            rs = sp - ls
            pbt = f"{' ' * 3}{' ' * ls}{options[po]}{' ' * rs}{' ' * 3}"
            safe_addstr(stdscr, oy+po*2, (mx-len(pbt))//2, pbt, st)
            
            # Redraw current selection (selected)
            st = curses.color_pair(5)|curses.A_BOLD
            sp = mol - len(options[co])
            ls = sp // 2
            rs = sp - ls
            nbt = f"{' ' * 3}{' ' * ls}{options[co]}{' ' * rs}{' ' * 3}"
            safe_addstr(stdscr, oy+co*2, (mx-len(nbt))//2, nbt, st)
            
            po = co
            
        stdscr.refresh()
        
        try:
            # Get keypress
            k = stdscr.getch()
            
            if k in [ord('q'), ord('Q'), 27]:  # q, Q, or ESC
                break
            elif k == curses.KEY_UP and co > 0:
                co -= 1
            elif k == curses.KEY_DOWN and co < len(options) - 1:
                co += 1
            elif k in [curses.KEY_ENTER, ord('\n'), ord('\r')]:
                if co == 0:
                    return "snake"
                elif co == 1:
                    return "tetris"
                elif co == 2:
                    return "pong"
        except KeyboardInterrupt:
            break
            
    return "exit"

def reload_module(module_name):
    """Force reload a module to ensure we get a fresh instance."""
    # Import the module if needed
    if module_name not in sys.modules:
        return importlib.import_module(module_name)
    
    # Otherwise reload it
    return importlib.reload(sys.modules[module_name])

def run_game(game_name):
    """Run a game with fresh module state.
    
    Returns:
        bool: True if we should return to menu, False if we should exit completely
    """
    # Force reload the appropriate module
    if game_name == "snake":
        # Force reload the module to get a fresh instance
        snake_module = reload_module("terminaide.demos.snake")
        # Reset module-level state
        snake_module._exit_requested = False
        snake_module._stdscr = None
        # Run the game with the from_index flag
        result = snake_module.run_demo(from_index=True)
        # Return True if we should go back to menu
        return result == "back_to_menu"
        
    elif game_name == "tetris":
        tetris_module = reload_module("terminaide.demos.tetris")
        tetris_module._exit_requested = False
        tetris_module._stdscr = None
        result = tetris_module.run_demo(from_index=True)
        return result == "back_to_menu"
        
    elif game_name == "pong":
        pong_module = reload_module("terminaide.demos.pong")
        pong_module.exit_requested = False
        pong_module._stdscr = None
        result = pong_module.run_demo(from_index=True)
        return result == "back_to_menu"
    
    # Default: don't return to menu
    return False

def run_demo():
    """Main entry point for the demo."""
    global _exit_requested
    
    # Set up signal handler for clean exit
    signal.signal(signal.SIGINT, handle_exit)
    
    try:
        while True:
            # Show menu
            choice = curses.wrapper(index_menu)
            
            # Exit if requested
            if choice == "exit" or _exit_requested:
                cleanup()
                return
                
            # End curses mode before running games
            if _stdscr:
                curses.endwin()
                
            # Run the selected game with fresh module state
            # If it returns True, we should go back to menu; otherwise exit
            return_to_menu = run_game(choice)
            
            if not return_to_menu:
                # Normal game exit - exit the program
                break
            # Otherwise continue the loop (show menu again)
            
    except Exception as e:
        print(f"\n\033[31mError in index demo: {e}\033[0m")
    finally:
        _exit_requested = True
        cleanup()

if __name__ == "__main__":
    print("\033[?25l\033[2J\033[H", end="")
    try:
        run_demo()
    finally:
        cleanup()