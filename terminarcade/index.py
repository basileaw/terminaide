# index.py

import curses
import signal
import sys
import importlib

stdscr = None
exit_requested = False


def handle_exit(sig, frame):
    """Handle SIGINT (Ctrl+C) for clean program exit."""
    global exit_requested
    exit_requested = True


def cleanup():
    """Restore terminal state and print goodbye message."""
    if stdscr:
        try:
            curses.endwin()
            print("\033[?25l\033[2J\033[H", end="")
            try:
                rows, cols = stdscr.getmaxyx()
            except:
                rows, cols = 24, 80
            msg = "Thank you for using terminaide"
            print("\033[2;{}H{}".format((cols - len(msg)) // 2, msg))
            print("\033[3;{}H{}".format((cols - len("Goodbye!")) // 2, "Goodbye!"))
            sys.stdout.flush()
        except:
            pass


def safe_addstr(win, y, x, text, attr=0):
    """Safely add a string to the screen, handling boundary conditions."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    ml = w - x
    if ml <= 0:
        return
    t = text[:ml]
    try:
        win.addstr(y, x, t, attr)
    except:
        curses.error


def draw_horizontal_line(win, y, x, width, attr=0):
    """Draw a horizontal line on the screen."""
    for i in range(width):
        safe_addstr(win, y, x + i, " ", attr)


def _index_menu_loop(stdscr_param):
    """Main menu interface.

    Args:
        stdscr_param: The curses window.

    Returns:
        str: Game to run ("snake", "tetris", "pong", or "exit").
    """
    global stdscr, exit_requested
    stdscr = stdscr_param
    exit_requested = False

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
    curses.init_pair(7, curses.COLOR_BLUE, -1)  # For the GitHub URL

    curses.curs_set(0)  # Hide cursor

    # Setup screen
    stdscr.clear()
    options = ["Snake", "Tetris", "Pong"]
    current_option = 0  # Current option
    previous_option = 0  # Previous option

    # Get screen dimensions
    my, mx = stdscr.getmaxyx()

    # Title ASCII art options based on screen width
    title_lines = [
        "████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗      █████╗ ██████╗  ██████╗ █████╗ ██████╗ ███████╗",
        "╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║     ██╔══██╗██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝",
        "   ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║     ███████║██████╔╝██║     ███████║██║  ██║█████╗  ",
        "   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║     ██╔══██║██╔══██╗██║     ██╔══██║██║  ██║██╔══╝  ",
        "   ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║     ██║  ██║██║  ██║╚██████╗██║  ██║██████╔╝███████╗",
        "   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝     ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═════╝ ╚══════╝",
    ]

    simple_title_lines = [
        " _____              _         _                   _      ",
        "|_   _|__ _ __ _ __ (_)_ __   /_\\  _ __ ___ __ _  _| | ___ ",
        "  | |/ _ \\ '__| '_ \\| | '_ \\ //_\\\\| '__/ __/ _` |/ _` |/ _ \\",
        "  | |  __/ |  | | | | | | | /  _ \\ | | (_| (_| | (_| |  __/",
        "  |_|\\___|_|  |_| |_|_|_| |_\\_/ \\_\\_|  \\___\\__,_|\\__,_|\\___|",
    ]

    very_simple_title = [
        "==============================",
        "||     TERMIN-ARCADE       ||",
        "==============================",
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
            safe_addstr(
                stdscr,
                1 + i,
                (mx - len(line)) // 2,
                line,
                curses.color_pair(1) | curses.A_BOLD,
            )

    # Calculate starting Y position after the title
    sy = 2 + len(title_to_use)

    # Draw instructions
    instr = "Use ←/→ to navigate, Enter to select, Q to quit"
    safe_addstr(stdscr, sy + 1, (mx - len(instr)) // 2, instr, curses.color_pair(2))

    # Add backspace/delete instruction
    back_instr = "Press Backspace or Delete in games to return to this menu"
    safe_addstr(
        stdscr,
        sy + 2,
        (mx - len(back_instr)) // 2,
        back_instr,
        curses.color_pair(6) | curses.A_BOLD,
    )

    # Calculate menu layout for horizontal buttons
    # We'll compute the total width needed for all buttons with padding between them
    button_padding = 4  # Spaces between buttons
    button_width = max(len(o) for o in options) + 6  # +6 for padding inside each button
    total_buttons_width = (button_width * len(options)) + (
        button_padding * (len(options) - 1)
    )

    # Center the row of buttons
    start_x = (mx - total_buttons_width) // 2
    menu_y = sy + 4  # The y position for the row of buttons

    # Initial draw of menu options horizontally
    for i, option in enumerate(options):
        button_x = start_x + (i * (button_width + button_padding))
        st = curses.color_pair(5) if i == current_option else curses.color_pair(4)

        # Center the text within the button
        text_padding = (button_width - len(option)) // 2
        button_text = (
            " " * text_padding
            + option
            + " " * (button_width - len(option) - text_padding)
        )

        safe_addstr(stdscr, menu_y, button_x, button_text, st | curses.A_BOLD)

    # Add GitHub URL below the buttons
    github_url = "https://github.com/bazeindustries/terminaide"
    safe_addstr(
        stdscr,
        menu_y + 2,  # 2 lines below the buttons
        (mx - len(github_url)) // 2,
        github_url,
        curses.color_pair(7) | curses.A_BOLD,
    )

    # Main menu loop
    while True:
        if exit_requested:
            break

        # Update menu selection if changed
        if current_option != previous_option:
            # Redraw previous selection (unselected)
            prev_button_x = start_x + (
                previous_option * (button_width + button_padding)
            )
            st = curses.color_pair(4) | curses.A_BOLD
            prev_option = options[previous_option]
            text_padding = (button_width - len(prev_option)) // 2
            button_text = (
                " " * text_padding
                + prev_option
                + " " * (button_width - len(prev_option) - text_padding)
            )
            safe_addstr(stdscr, menu_y, prev_button_x, button_text, st)

            # Redraw current selection (selected)
            curr_button_x = start_x + (current_option * (button_width + button_padding))
            st = curses.color_pair(5) | curses.A_BOLD
            curr_option = options[current_option]
            text_padding = (button_width - len(curr_option)) // 2
            button_text = (
                " " * text_padding
                + curr_option
                + " " * (button_width - len(curr_option) - text_padding)
            )
            safe_addstr(stdscr, menu_y, curr_button_x, button_text, st)

            previous_option = current_option

        stdscr.refresh()

        try:
            # Get keypress
            k = stdscr.getch()

            if k in [ord("q"), ord("Q"), 27]:  # q, Q, or ESC
                break
            elif k in [curses.KEY_LEFT, ord("a"), ord("A")] and current_option > 0:
                current_option -= 1
            elif (
                k in [curses.KEY_RIGHT, ord("d"), ord("D")]
                and current_option < len(options) - 1
            ):
                current_option += 1
            elif k in [curses.KEY_ENTER, ord("\n"), ord("\r")]:
                if current_option == 0:
                    return "snake"
                elif current_option == 1:
                    return "tetris"
                elif current_option == 2:
                    return "pong"
        except KeyboardInterrupt:
            break

    return "exit"


def reload_module(module_name):
    """Force reload a module to ensure we get a fresh instance.

    Args:
        module_name: Name of the module to reload.

    Returns:
        The reloaded module.
    """
    # Import the module if needed
    if module_name not in sys.modules:
        return importlib.import_module(module_name)

    # Otherwise reload it
    return importlib.reload(sys.modules[module_name])


def run_game(game_name):
    """Run a game with fresh module state.

    Args:
        game_name: Name of the game to run ("snake", "tetris", "pong").

    Returns:
        bool: True if we should return to menu, False if we should exit completely.
    """
    # Force reload the appropriate module
    if game_name == "snake":
        # Force reload the module to get a fresh instance
        snake_module = reload_module("terminarcade.snake")
        # Reset module-level state
        snake_module.exit_requested = False
        snake_module.stdscr = None
        # Run the game with the from_index flag
        result = snake_module.play_snake(from_index=True)
        # Return True if we should go back to menu
        return result == "back_to_menu"

    elif game_name == "tetris":
        tetris_module = reload_module("terminarcade.tetris")
        tetris_module.exit_requested = False
        tetris_module.stdscr = None
        result = tetris_module.play_tetris(from_index=True)
        return result == "back_to_menu"

    elif game_name == "pong":
        pong_module = reload_module("terminarcade.pong")
        pong_module.exit_requested = False
        pong_module.stdscr = None
        result = pong_module.play_pong(from_index=True)
        return result == "back_to_menu"

    # Default: don't return to menu
    return False


def show_index():
    """Main entry point for the game menu.

    This is the main public-facing function for showing the game menu.

    Returns:
        None
    """
    global exit_requested

    # Set up signal handler for clean exit
    signal.signal(signal.SIGINT, handle_exit)

    try:
        while True:
            # Show menu
            choice = curses.wrapper(_index_menu_loop)

            # Exit if requested
            if choice == "exit" or exit_requested:
                cleanup()
                return

            # End curses mode before running games
            if stdscr:
                curses.endwin()

            # Run the selected game with fresh module state
            # If it returns True, we should go back to menu; otherwise exit
            return_to_menu = run_game(choice)

            if not return_to_menu:
                # Normal game exit - exit the program
                break
            # Otherwise continue the loop (show menu again)

    except Exception as e:
        print(f"\n\033[31mError in index: {e}\033[0m")
    finally:
        exit_requested = True
        cleanup()


if __name__ == "__main__":
    print("\033[?25l\033[2J\033[H", end="")
    try:
        show_index()
    finally:
        cleanup()
