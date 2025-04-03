# instructions.py 

import curses
import time
import signal
import sys
import os

_stdscr = None
_exit_requested = False  # Set by the SIGINT handler when Ctrl+C is pressed.

def handle_exit(sig, frame):
    global _exit_requested
    _exit_requested = True

def cleanup():
    if _stdscr is not None:
        try:
            curses.endwin()
            # Hide cursor instead of making it visible
            print("\033[?25l", end="")
            sys.stdout.flush()
        except:
            pass

def instructions(stdscr):
    global _stdscr
    _stdscr = stdscr
    signal.signal(signal.SIGINT, handle_exit)
    
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.curs_set(0)

    ascii_banner = [
        "████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗ █████╗ ██╗██████╗ ███████╗",
        "╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║██╔══██╗██║██╔══██╗██╔════╝",
        "   ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║███████║██║██║  ██║█████╗  ",
        "   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██╔══██║██║██║  ██║██╔══╝  ",
        "   ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║██║  ██║██║██████╔╝███████╗",
        "   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝╚═════╝ ╚══════╝",
    ]

    instructions_before = [
        "You're seeing this message because no client script or terminal routes were configured.",
        "Terminaide offers these simple ways to get started:",
        "",
    ]

    # Function mode example (left side)
    function_snippet = [
        "FUNCTION MODE:",
        "# Serve a Python function directly",
        "",
        "from terminaide import serve_function",
        "",
        "def hello():",
        "    name = input(\"What's your name? \")",
        "    print(f\"Hello, {name}!\")",
        "",
        "serve_function(hello)  # That's it!",
    ]

    # Script mode example (right side)
    script_snippet = [
        "SCRIPT MODE:",
        "# Serve a Python script file",
        "",
        "from terminaide import serve_script",
        "",
        "# Run an existing script in a browser",
        "serve_script(\"my_script.py\")",
        "",
        "",
        "",
    ]

    # CHANGED HERE: Updated text to say “Press Enter to exit this screen.”
    instructions_after = [
        "",
        "For more advanced usage (like integration with FastAPI),",
        "please consult the documentation.",
        "",
        "Press Enter to exit this screen.",
    ]

    height, width = stdscr.getmaxyx()
    start_y = 2

    try:
        stdscr.clear()
        
        # Print banner, centering each banner line
        for i, line in enumerate(ascii_banner):
            x = max((width - len(line)) // 2, 0)
            try:
                stdscr.addstr(start_y + i, x, line, curses.color_pair(1))
            except curses.error:
                pass
        start_y += len(ascii_banner) + 1
        
        # Print the "before" lines, centering them individually:
        for i, line in enumerate(instructions_before):
            if _exit_requested:
                break
            x = max((width - len(line)) // 2, 0)
            try:
                stdscr.addstr(start_y + i, x, line, curses.color_pair(1))
                stdscr.refresh()
                time.sleep(0.02)
            except curses.error:
                pass
        start_y += len(instructions_before)

        # Determine box widths from snippet lines.
        func_max_len = max(len(line) for line in function_snippet)
        script_max_len = max(len(line) for line in script_snippet)
        needed_box_width = max(func_max_len, script_max_len) + 4  # +4 for margin

        # If terminal is too narrow, fall back to half of the screen
        total_needed = needed_box_width * 2 + 4  # two boxes + gap
        if total_needed > width - 2:
            left_width = right_width = (width // 2) - 4
        else:
            left_width = right_width = needed_box_width
        
        # Center both boxes side-by-side
        total_box_width = left_width + right_width + 4  # gap of 4
        center_x = (width - total_box_width) // 2
        left_x = center_x
        right_x = left_x + left_width + 4

        # Draw the boxes (top borders)
        try:
            # Left box
            left_border = "+" + "-" * left_width + "+"
            stdscr.addstr(start_y, left_x, left_border)
            
            # Right box
            right_border = "+" + "-" * right_width + "+"
            stdscr.addstr(start_y, right_x, right_border)
        except curses.error:
            pass
        
        # Content lines
        box_height = max(len(function_snippet), len(script_snippet))
        for i in range(box_height):
            if _exit_requested:
                break
                
            y = start_y + i + 1
            
            # Left box content
            try:
                if i < len(function_snippet):
                    line = function_snippet[i]
                    stdscr.addstr(y, left_x, "| " + line)
                    right_pos = left_x + left_width
                    stdscr.addstr(y, right_pos, " |")
                else:
                    stdscr.addstr(y, left_x, "| ")
                    stdscr.addstr(y, left_x + left_width, " |")
            except curses.error:
                pass
                
            # Right box content
            try:
                if i < len(script_snippet):
                    line = script_snippet[i]
                    stdscr.addstr(y, right_x, "| " + line)
                    right_pos = right_x + right_width
                    stdscr.addstr(y, right_pos, " |")
                else:
                    stdscr.addstr(y, right_x, "| ")
                    stdscr.addstr(y, right_x + right_width, " |")
            except curses.error:
                pass
        
        # Bottom borders
        try:
            y = start_y + box_height + 1
            left_border = "+" + "-" * left_width + "+"
            stdscr.addstr(y, left_x, left_border)
            
            right_border = "+" + "-" * right_width + "+"
            stdscr.addstr(y, right_x, right_border)
        except curses.error:
            pass
        
        # Update position for footer text
        start_y += box_height + 3
        
        # Print "after" lines, centered line by line
        for i, line in enumerate(instructions_after):
            if _exit_requested:
                break
            x = max((width - len(line)) // 2, 0)
            try:
                stdscr.addstr(start_y + i, x, line, curses.color_pair(1))
                stdscr.refresh()
                time.sleep(0.02)
            except curses.error:
                pass

        # CHANGED HERE: wait specifically for Enter (ASCII 10 or 13)
        if not _exit_requested:
            stdscr.nodelay(False)
            while True:
                if _exit_requested:
                    break
                ch = stdscr.getch()
                # ch == 10 -> Line Feed (Linux), ch == 13 -> Carriage Return (Windows)
                if ch in (10, 13):
                    break

    except KeyboardInterrupt:
        pass
    finally:
        cleanup()

if __name__ == "__main__":
    print("\033[?25l", end="")  # Hide cursor
    os.environ.setdefault('NCURSES_NO_SETBUF', '1')
    
    try:
        curses.wrapper(instructions)
    finally:
        cleanup()
