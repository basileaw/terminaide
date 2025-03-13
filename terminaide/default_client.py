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
            # Make cursor visible again
            print("\033[?25h", end="")
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
        "You're seeing this message because no client script, terminal routes, or server routes were configured.",
        "To serve a Python app with Terminaide, provide a path to your app when calling serve_terminal().",
        "Your client script should contain the logic you want to run in the terminal session. Like this:",
        ""
    ]

    # Code snippet lines
    code_snippet = [
        "",
        "serve_terminal(",
        "    app,",
        '    client_script="script_1.py"',
        "    terminal_routes={",
        '        "/cli2": "script2.py",',
        '        "/cli3": ["script3.py", "--arg1", "value"],',
        '        "/cli4": {',
        '            "client_script": "script4.py",',
        '            "title": "Advanced CLI"',
        "        }",
        ")",
        "",
    ]

    instructions_after = [
        ""
    ]

    height, width = stdscr.getmaxyx()
    start_y = 2

    try:
        stdscr.clear()
        
        # Print banner, centering each banner line
        for i, line in enumerate(ascii_banner):
            x = max((width - len(line)) // 2, 0)
            stdscr.addstr(start_y + i, x, line, curses.color_pair(1))
        start_y += len(ascii_banner) + 1
        
        # Print "before" lines, centering them individually:
        for i, line in enumerate(instructions_before):
            if _exit_requested:
                break
            x = max((width - len(line)) // 2, 0)
            stdscr.addstr(start_y + i, x, line, curses.color_pair(1))
            stdscr.refresh()
            time.sleep(0.02)
        start_y += len(instructions_before)

        #
        # 1) Build the ASCII box around the snippet
        #
        max_snippet_len = max(len(line) for line in code_snippet)  # find widest line
        top_border = "+" + "-" * (max_snippet_len + 2) + "+"       # e.g. +----------+
        bottom_border = top_border                                 # same as top

        # 2) The total width for this "box" is the length of top_border
        box_width = len(top_border)

        # 3) Calculate offset so entire box is centered
        snippet_offset_x = max((width - box_width) // 2, 0)

        # 4) Print the top border
        stdscr.addstr(start_y, snippet_offset_x, top_border, curses.color_pair(1))
        start_y += 1

        # 5) Print each snippet line inside the box
        for snippet_line in code_snippet:
            if _exit_requested:
                break
            # Pad each line so they match max_snippet_len
            line_with_spaces = snippet_line + " " * (max_snippet_len - len(snippet_line))
            box_line = "| " + line_with_spaces + " |"
            stdscr.addstr(start_y, snippet_offset_x, box_line, curses.color_pair(1))
            stdscr.refresh()
            time.sleep(0.02)
            start_y += 1

        # 6) Print bottom border
        stdscr.addstr(start_y, snippet_offset_x, bottom_border, curses.color_pair(1))
        start_y += 2  # leave a blank line after the box

        # Print "after" lines, centered line by line
        for i, line in enumerate(instructions_after):
            if _exit_requested:
                break
            x = max((width - len(line)) // 2, 0)
            stdscr.addstr(start_y + i, x, line, curses.color_pair(1))
            stdscr.refresh()
            time.sleep(0.02)

        if not _exit_requested:
            stdscr.nodelay(False)
            stdscr.getch()

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
