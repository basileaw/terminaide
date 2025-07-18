# monitor.py

import os
import sys
import subprocess
import threading
import tempfile
import signal
import json
from pathlib import Path
from typing import Optional


def _get_package_cache_dir() -> Path:
    """Get package-based cache directory for monitor logs."""
    package_root = Path(__file__).parent.parent  # terminaide/
    logs_dir = package_root / "cache" / "logs"
    logs_dir.mkdir(exist_ok=True, parents=True)  # Ensure directory exists
    return logs_dir


def _resolve_monitor_log_path(config_path: Optional[Path] = None) -> Path:
    """Resolve monitor log path in priority order."""
    
    # 1. Explicit config parameter (highest priority)
    if config_path:
        try:
            config_path.parent.mkdir(exist_ok=True, parents=True)
            # Test if we can write to the directory
            test_file = config_path.parent / f".write_test_{os.getpid()}"
            test_file.touch()
            test_file.unlink()
            return config_path
        except (PermissionError, OSError) as e:
            raise RuntimeError(f"Configured monitor log path not writable: {config_path}") from e
    
    # 2. Environment variable override
    if env_path := os.environ.get("TERMINAIDE_MONITOR_LOG"):
        log_path = Path(env_path)
        try:
            log_path.parent.mkdir(exist_ok=True, parents=True)
            # Test if we can write to the directory
            test_file = log_path.parent / f".write_test_{os.getpid()}"
            test_file.touch()
            test_file.unlink()
            return log_path
        except (PermissionError, OSError) as e:
            raise RuntimeError(f"Environment monitor log path not writable: {log_path}") from e
    
    # 3. Package cache (only fallback)
    try:
        cache_dir = _get_package_cache_dir()
        cache_dir.mkdir(exist_ok=True, parents=True)
        log_path = cache_dir / "monitor.log"
        # Test if we can write to the directory
        test_file = cache_dir / f".write_test_{os.getpid()}"
        test_file.touch()
        test_file.unlink()
        return log_path
    except (PermissionError, OSError) as e:
        raise RuntimeError(
            f"Package cache directory not writable and no explicit monitor log configured: {cache_dir}. "
            "To use external directories, set monitor_log_path in TerminaideConfig or "
            "set the TERMINAIDE_MONITOR_LOG environment variable."
        ) from e


class ServerMonitor:
    """
    A reusable, object-oriented monitor for logging and displaying process output.
    """

    def __init__(self, output_file=None, title=None, config=None):
        """
        Initialize Monitor instance.

        Args:
            output_file: Path to the log file (optional, defaults to package cache)
            title: Main title for monitor display (triggers auto-write if provided)
            config: Optional TerminaideConfig with monitor_log_path setting
        """
        if output_file is None:
            # Use config.monitor_log_path if available
            config_path = getattr(config, 'monitor_log_path', None) if config else None
            self.output_file = str(_resolve_monitor_log_path(config_path))
        else:
            self.output_file = output_file

        # Always start monitoring (with default title if none provided)
        self.write(title=title or "MONITOR")

    def write(self, title="MONITOR"):
        """Set up monitoring and restart if needed"""
        _monitor_write(self.output_file, title)


def monitor_read_standalone(output_file=None, use_curses=True):
    """
    Completely self-contained monitor reader function for terminaide extraction.
    This function includes all necessary imports and logic inline, making it
    perfect for ephemeral scripts without any external dependencies.

    Args:
        output_file: Path to the log file (optional, defaults to temp directory)
        use_curses: Whether to use curses interface for reading (default: True)
    """
    # All imports needed for this function
    import os
    import sys
    import threading
    import time
    import tempfile
    import curses
    import re
    import locale
    import json
    from collections import deque
    import queue
    from pathlib import Path

    # Set default output file
    if output_file is None:
        output_file = str(_resolve_monitor_log_path())

    # Ensure the log file exists - create empty one if not
    output_path = Path(output_file)
    if not output_path.exists():
        output_path.parent.mkdir(exist_ok=True, parents=True)
        config_header = f"MONITOR_CONFIG: {json.dumps({'title': 'MONITOR'})}\n--- LOG START ---\n"
        with open(output_path, "w") as f:
            f.write(config_header)

    # Extract config from log file, fallback to defaults
    title = "MONITOR"

    try:
        with open(output_file, "r") as f:
            first_line = f.readline()
            if first_line.startswith("MONITOR_CONFIG: "):
                config_json = first_line[
                    16:
                ].strip()  # Remove "MONITOR_CONFIG: " prefix
                config = json.loads(config_json)
                title = config.get("title", title)
    except (FileNotFoundError, json.JSONDecodeError, Exception):
        # Use defaults if config extraction fails
        pass

    def should_display_line(line):
        """Filter out config header lines from display"""
        if line.startswith("MONITOR_CONFIG: "):
            return False
        if line.strip() == "--- LOG START ---":
            return False
        return True

    def strip_ansi(text):
        """Remove ANSI escape sequences from text"""
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_escape.sub("", text)

    def parse_ansi_colors(text):
        """Parse ANSI color codes and return segments with color info"""
        ansi_pattern = re.compile(r"\x1B\[([0-9;]*)m")

        segments = []
        last_end = 0
        current_fg = curses.COLOR_WHITE
        current_bg = -1  # Default background
        bold = False

        for match in ansi_pattern.finditer(text):
            # Add text before this color code
            if match.start() > last_end:
                segments.append(
                    {
                        "text": text[last_end : match.start()],
                        "fg": current_fg,
                        "bg": current_bg,
                        "bold": bold,
                    }
                )

            # Parse color codes
            codes = match.group(1).split(";") if match.group(1) else ["0"]
            for code in codes:
                if code == "" or code == "0":  # Reset
                    current_fg = curses.COLOR_WHITE
                    current_bg = -1
                    bold = False
                elif code == "1":  # Bold
                    bold = True
                elif code == "22":  # Normal intensity
                    bold = False
                elif code in [
                    "30",
                    "31",
                    "32",
                    "33",
                    "34",
                    "35",
                    "36",
                    "37",
                ]:  # Foreground colors
                    color_map = {
                        "30": curses.COLOR_BLACK,
                        "31": curses.COLOR_RED,
                        "32": curses.COLOR_GREEN,
                        "33": curses.COLOR_YELLOW,
                        "34": curses.COLOR_BLUE,
                        "35": curses.COLOR_MAGENTA,
                        "36": curses.COLOR_CYAN,
                        "37": curses.COLOR_WHITE,
                    }
                    current_fg = color_map[code]
                elif code in [
                    "90",
                    "91",
                    "92",
                    "93",
                    "94",
                    "95",
                    "96",
                    "97",
                ]:  # Bright foreground colors
                    color_map = {
                        "90": curses.COLOR_BLACK,
                        "91": curses.COLOR_RED,
                        "92": curses.COLOR_GREEN,
                        "93": curses.COLOR_YELLOW,
                        "94": curses.COLOR_BLUE,
                        "95": curses.COLOR_MAGENTA,
                        "96": curses.COLOR_CYAN,
                        "97": curses.COLOR_WHITE,
                    }
                    current_fg = color_map[code]
                elif code in [
                    "40",
                    "41",
                    "42",
                    "43",
                    "44",
                    "45",
                    "46",
                    "47",
                ]:  # Background colors
                    color_map = {
                        "40": curses.COLOR_BLACK,
                        "41": curses.COLOR_RED,
                        "42": curses.COLOR_GREEN,
                        "43": curses.COLOR_YELLOW,
                        "44": curses.COLOR_BLUE,
                        "45": curses.COLOR_MAGENTA,
                        "46": curses.COLOR_CYAN,
                        "47": curses.COLOR_WHITE,
                    }
                    current_bg = color_map[code]

            last_end = match.end()

        # Add remaining text
        if last_end < len(text):
            segments.append(
                {
                    "text": text[last_end:],
                    "fg": current_fg,
                    "bg": current_bg,
                    "bold": bold,
                }
            )

        return segments

    def get_color_pair(fg, bg, bold, color_pairs):
        """Get or create a color pair for the given colors"""
        # Create a key for this color combination
        key = (fg, bg, bold)

        if key not in color_pairs:
            pair_id = len(color_pairs) + 3  # Start after our reserved pairs (1, 2)
            if pair_id < curses.COLOR_PAIRS:
                try:
                    curses.init_pair(pair_id, fg, bg)
                    color_pairs[key] = pair_id
                except curses.error:
                    # Fallback to default colors if we can't create the pair
                    color_pairs[key] = 0
            else:
                color_pairs[key] = 0

        return color_pairs[key]

    def _generate_banner(width, title, output_file=None):
        """Generate banner lines for display"""
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.align import Align
            from terminaide import terminascii

            console = Console(width=width, legacy_windows=False)
            server_banner = terminascii(title)
            centered_banner = Align.center(server_banner)

            # Build panel kwargs dynamically
            panel_kwargs = {
                "border_style": "blue",
                "expand": True,
                "padding": [1, 1],
            }
            panel_kwargs["title"] = "[bold green]SERVER[/bold green]"
            panel_kwargs["title_align"] = "left"
            panel_kwargs["subtitle"] = "[bold green]MONITOR[/bold green]"
            panel_kwargs["subtitle_align"] = "right"

            panel = Panel(centered_banner, **panel_kwargs)

            with console.capture() as capture:
                console.print(panel)

            banner_text = capture.get()
            banner_lines = banner_text.split("\n")

            # Remove empty trailing lines
            while banner_lines and not banner_lines[-1].strip():
                banner_lines.pop()

            return banner_lines

        except Exception:
            # Fallback to simple banner
            return [
                "=" * min(50, width),
                "SERVER MONITOR",
                f"File: {os.path.basename(output_file)}",
                "=" * min(50, width),
            ]

    def simple_monitor_read():
        """Simple file reader without curses"""
        try:
            with open(output_file, "rb") as file:
                # First, print existing content (filtered)
                contents = file.read()
                if contents:
                    lines = contents.decode("utf-8", errors="replace").splitlines(
                        keepends=True
                    )
                    for line in lines:
                        if should_display_line(line.rstrip("\n\r")):
                            sys.stdout.write(line)
                    sys.stdout.flush()

                # Track file size for truncation detection
                last_size = file.tell()

                # Follow the file
                while True:
                    # Check current file size
                    file.seek(0, os.SEEK_END)
                    current_size = file.tell()

                    # If file was truncated (e.g., overwritten), start from beginning
                    if current_size < last_size:
                        file.seek(0)
                        last_size = 0
                    else:
                        # Go back to where we were
                        file.seek(last_size)

                    # Read new data (filtered)
                    new_data = file.read()
                    if new_data:
                        lines = new_data.decode("utf-8", errors="replace").splitlines(
                            keepends=True
                        )
                        for line in lines:
                            if should_display_line(line.rstrip("\n\r")):
                                sys.stdout.write(line)
                        sys.stdout.flush()
                        last_size = file.tell()
                    else:
                        # No new data, sleep briefly
                        time.sleep(0.1)

        except FileNotFoundError:
            print(f"Error: The file '{output_file}' was not found.")
        except KeyboardInterrupt:
            print("\n\nStopped following log file.")
        except Exception as e:
            print(f"Error reading file: {e}")

    def curses_monitor_read():
        """Curses-based file reader with rich interface"""
        # Enable wide-character support for UTF-8 box-drawing characters
        locale.setlocale(locale.LC_ALL, "")

        def curses_main(stdscr):
            # Setup curses
            curses.curs_set(0)  # Hide cursor
            stdscr.nodelay(True)  # Non-blocking getch()
            stdscr.timeout(50)  # Faster timeout for smoother scrolling

            # Initialize colors if available
            if curses.has_colors():
                curses.start_color()
                curses.use_default_colors()
                # Define color pairs for header
                curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)
                curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLUE)

            # Get initial dimensions
            height, width = stdscr.getmaxyx()

            # Generate banner
            banner_lines = _generate_banner(width, title, output_file)

            footer_height = 1
            header_height = len(banner_lines) + 1  # +1 for spacing
            content_height = height - header_height - footer_height

            # Create persistent windows with proper dimensions
            content_win = curses.newwin(content_height, width, header_height, 0)
            footer_win = curses.newwin(footer_height, width, height - footer_height, 0)

            # Content buffer and display parameters
            content_buffer = deque(maxlen=10000)  # Keep last 10k lines
            display_offset = 0  # For scrolling
            file_queue = queue.Queue()
            stop_event = threading.Event()
            color_pairs = {}  # Cache for color pairs

            # Track what's currently displayed to minimize redraws
            displayed_lines = {}  # row -> (start_idx, line_content)
            last_footer_text = ""  # Track footer to avoid unnecessary updates
            last_total_lines = 0

            def file_reader():
                """Read file in background thread"""
                try:
                    with open(output_file, "rb") as file:
                        # Read existing content
                        contents = file.read()
                        if contents:
                            lines = contents.decode(
                                "utf-8", errors="replace"
                            ).splitlines()
                            for line in lines:
                                if should_display_line(line):
                                    file_queue.put(("line", line))

                        last_size = file.tell()

                        while not stop_event.is_set():
                            file.seek(0, os.SEEK_END)
                            current_size = file.tell()

                            if current_size < last_size:
                                # File truncated, restart from beginning
                                file.seek(0)
                                last_size = 0
                                file_queue.put(("clear", None))
                            else:
                                file.seek(last_size)

                            new_data = file.read()
                            if new_data:
                                lines = new_data.decode(
                                    "utf-8", errors="replace"
                                ).splitlines()
                                for line in lines:
                                    if should_display_line(line):
                                        file_queue.put(("line", line))
                                last_size = file.tell()

                            time.sleep(0.1)
                except Exception as e:
                    file_queue.put(("error", str(e)))

            # Start file reader thread
            reader_thread = threading.Thread(target=file_reader, daemon=True)
            reader_thread.start()

            # Draw banner directly to main screen with colors
            for i, line in enumerate(banner_lines):
                if i < header_height - 1:  # Leave space for content
                    if curses.has_colors():
                        # Parse ANSI colors and display with colors
                        segments = parse_ansi_colors(line)
                        col = 0
                        for segment in segments:
                            if segment["text"] and col < width:
                                text = segment["text"][: width - col]
                                if text:
                                    try:
                                        pair_id = get_color_pair(
                                            segment["fg"],
                                            segment["bg"],
                                            segment["bold"],
                                            color_pairs,
                                        )
                                        attrs = curses.color_pair(pair_id)
                                        if segment["bold"]:
                                            attrs |= curses.A_BOLD
                                        stdscr.addstr(i, col, text, attrs)
                                        col += len(text)
                                    except curses.error:
                                        break
                    else:
                        # Fallback to plain text
                        clean_line = strip_ansi(line)
                        try:
                            stdscr.addstr(i, 0, clean_line[:width])
                        except curses.error:
                            pass
            stdscr.noutrefresh()

            # Draw initial footer
            controls = " [q]uit [↑↓]scroll [Home/End]jump "

            # Initial atomic update with empty content
            if curses.has_colors():
                footer_win.bkgd(" ", curses.color_pair(2))
            footer_win.noutrefresh()
            content_win.noutrefresh()
            curses.doupdate()

            # Main display loop
            while True:
                # Check for terminal resize
                new_height, new_width = stdscr.getmaxyx()
                if new_height != height or new_width != width:
                    height, width = new_height, new_width
                    content_height = height - header_height - footer_height

                    # Recreate windows with new dimensions
                    content_win = curses.newwin(content_height, width, header_height, 0)
                    footer_win = curses.newwin(
                        footer_height, width, height - footer_height, 0
                    )

                    # Reset display tracking for new window
                    displayed_lines.clear()
                    last_footer_text = ""
                    content_changed = True  # Force redraw after resize

                    # Regenerate and redraw banner for new width
                    banner_lines = _generate_banner(width, title, output_file)
                    header_height = len(banner_lines) + 1

                    # Clear and redraw banner
                    for i in range(header_height):
                        try:
                            stdscr.addstr(i, 0, " " * width)  # Clear line
                        except curses.error:
                            pass

                    # Redraw banner with colors
                    for i, line in enumerate(banner_lines):
                        if i < header_height - 1:
                            if curses.has_colors():
                                # Parse ANSI colors and display with colors
                                segments = parse_ansi_colors(line)
                                col = 0
                                for segment in segments:
                                    if segment["text"] and col < width:
                                        text = segment["text"][: width - col]
                                        if text:
                                            try:
                                                pair_id = get_color_pair(
                                                    segment["fg"],
                                                    segment["bg"],
                                                    segment["bold"],
                                                    color_pairs,
                                                )
                                                attrs = curses.color_pair(pair_id)
                                                if segment["bold"]:
                                                    attrs |= curses.A_BOLD
                                                stdscr.addstr(i, col, text, attrs)
                                                col += len(text)
                                            except curses.error:
                                                break
                            else:
                                # Fallback to plain text
                                clean_line = strip_ansi(line)
                                try:
                                    stdscr.addstr(i, 0, clean_line[:width])
                                except curses.error:
                                    pass
                    stdscr.noutrefresh()
                    curses.doupdate()

                # Process new lines from queue
                content_changed = False
                lines_processed = 0
                max_lines_per_update = 100  # Process up to 100 lines per update cycle

                while lines_processed < max_lines_per_update:
                    try:
                        msg_type, data = file_queue.get_nowait()
                        if msg_type == "line":
                            content_buffer.append(data)
                            content_changed = True
                            lines_processed += 1
                        elif msg_type == "clear":
                            content_buffer.clear()
                            display_offset = 0
                            content_changed = True
                            displayed_lines.clear()  # Clear display tracking
                            break  # Process clear immediately
                        elif msg_type == "error":
                            content_buffer.append(f"ERROR: {data}")
                            content_changed = True
                            lines_processed += 1
                    except queue.Empty:
                        break

                # Calculate visible lines
                total_lines = len(content_buffer)
                max_offset = max(0, total_lines - content_height)
                display_offset = min(display_offset, max_offset)

                # Handle keyboard input first
                scroll_changed = False
                try:
                    key = stdscr.getch()
                    if key == ord("q") or key == ord("Q"):
                        break
                    elif key == curses.KEY_UP:
                        new_offset = min(display_offset + 1, max_offset)
                        if new_offset != display_offset:
                            display_offset = new_offset
                            scroll_changed = True
                    elif key == curses.KEY_DOWN:
                        new_offset = max(display_offset - 1, 0)
                        if new_offset != display_offset:
                            display_offset = new_offset
                            scroll_changed = True
                    elif key == curses.KEY_PPAGE:  # Page Up
                        new_offset = min(display_offset + content_height, max_offset)
                        if new_offset != display_offset:
                            display_offset = new_offset
                            scroll_changed = True
                    elif key == curses.KEY_NPAGE:  # Page Down
                        new_offset = max(display_offset - content_height, 0)
                        if new_offset != display_offset:
                            display_offset = new_offset
                            scroll_changed = True
                    elif key == curses.KEY_HOME:
                        new_offset = max_offset
                        if new_offset != display_offset:
                            display_offset = new_offset
                            scroll_changed = True
                    elif key == curses.KEY_END:
                        new_offset = 0
                        if new_offset != display_offset:
                            display_offset = new_offset
                            scroll_changed = True
                except:
                    pass

                # Redraw content when content or scroll changes
                if content_changed or scroll_changed:
                    # Calculate which lines to show
                    start_idx = max(0, total_lines - content_height - display_offset)
                    end_idx = min(total_lines, start_idx + content_height)

                    # Track which rows need updating
                    rows_to_update = set()

                    # Check which lines have changed or need to be drawn
                    for row in range(content_height):
                        line_idx = start_idx + row if start_idx + row < end_idx else -1
                        current_display = displayed_lines.get(row, (-1, ""))

                        if line_idx == -1:
                            # This row should be empty
                            if current_display[0] != -1:
                                rows_to_update.add(row)
                        elif current_display[0] != line_idx or (
                            line_idx < len(content_buffer)
                            and current_display[1] != content_buffer[line_idx]
                        ):
                            # Line has changed
                            rows_to_update.add(row)

                    # Update only the rows that changed
                    for row in rows_to_update:
                        line_idx = start_idx + row if start_idx + row < end_idx else -1

                        if line_idx == -1 or line_idx >= len(content_buffer):
                            # Clear this row
                            content_win.move(row, 0)
                            content_win.clrtoeol()
                            displayed_lines[row] = (-1, "")
                        else:
                            # Draw the line
                            line = content_buffer[line_idx]

                            # Clear the row first (more efficient than overwriting)
                            content_win.move(row, 0)
                            content_win.clrtoeol()

                            if curses.has_colors():
                                # Parse ANSI colors and display with colors
                                segments = parse_ansi_colors(line)
                                col = 0
                                for segment in segments:
                                    if segment["text"] and col < width - 1:
                                        text = segment["text"][: width - 1 - col]
                                        if text:
                                            try:
                                                pair_id = get_color_pair(
                                                    segment["fg"],
                                                    segment["bg"],
                                                    segment["bold"],
                                                    color_pairs,
                                                )
                                                attrs = curses.color_pair(pair_id)
                                                if segment["bold"]:
                                                    attrs |= curses.A_BOLD
                                                content_win.addstr(
                                                    row, col, text, attrs
                                                )
                                                col += len(text)
                                            except curses.error:
                                                break
                            else:
                                # Fallback to plain text
                                clean_line = strip_ansi(line)
                                try:
                                    content_win.addnstr(row, 0, clean_line, width - 1)
                                except curses.error:
                                    pass

                            displayed_lines[row] = (line_idx, line)

                    content_win.noutrefresh()

                    # Update footer only if it changed
                    if total_lines > content_height:
                        scroll_pos = f" Lines: {total_lines} | Scroll: {display_offset}/{max_offset} "
                    else:
                        scroll_pos = f" Lines: {total_lines} "

                    footer_text = (
                        controls
                        + " " * (width - len(controls) - len(scroll_pos) - 1)
                        + scroll_pos
                    )

                    if (
                        footer_text != last_footer_text
                        or total_lines != last_total_lines
                    ):
                        # Footer has changed, update it
                        if curses.has_colors() and last_footer_text == "":
                            # Set background only once
                            footer_win.bkgd(" ", curses.color_pair(2))

                        footer_win.move(0, 0)
                        footer_win.clrtoeol()
                        try:
                            footer_win.addnstr(0, 0, footer_text, width - 1)
                        except curses.error:
                            pass
                        footer_win.noutrefresh()
                        last_footer_text = footer_text
                        last_total_lines = total_lines

                    # Single atomic update to eliminate flicker
                    curses.doupdate()

            # Cleanup
            stop_event.set()
            reader_thread.join(timeout=1)

        try:
            curses.wrapper(curses_main)
        except KeyboardInterrupt:
            print("\n\nStopped monitoring.")
        except FileNotFoundError:
            print(f"Error: The file '{output_file}' was not found.")
        except Exception as e:
            print(f"Error: {e}")

    # Main execution logic
    if use_curses:
        curses_monitor_read()
    else:
        simple_monitor_read()


def _monitor_write(output_file=None, title="MONITOR"):
    """Set up monitoring and restart if needed"""
    # Check if we're already in a monitored subprocess
    if os.environ.get("MONITORED_PROCESS"):
        # Just return - monitoring is already active
        return

    # Set default output file to package cache
    if output_file is None:
        output_file = str(_resolve_monitor_log_path())

    # Write config header to log file
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    config = {"title": title}
    config_header = f"MONITOR_CONFIG: {json.dumps(config)}\n--- LOG START ---\n"

    # Initialize log file with config
    with open(output_file, "w") as f:
        f.write(config_header)

    # Otherwise, restart this script with monitoring
    import pty

    master_fd, slave_fd = pty.openpty()

    def forward_output():
        with open(output_file, "ab") as log:
            while True:
                try:
                    data = os.read(master_fd, 1024)
                    if not data:
                        break
                    sys.stdout.buffer.write(data)
                    sys.stdout.flush()
                    log.write(data)
                    log.flush()
                except OSError:
                    break

    thread = threading.Thread(target=forward_output, daemon=True)
    thread.start()

    # Run this same script again with monitoring env var set
    env = os.environ.copy()
    env["MONITORED_PROCESS"] = "1"

    process = subprocess.Popen(
        [sys.executable] + sys.argv,
        stdout=slave_fd,
        stderr=slave_fd,
        stdin=sys.stdin,
        env=env,
        preexec_fn=os.setsid,  # Create new process group
    )

    os.close(slave_fd)

    # Set up signal handlers to forward to child process group
    def signal_handler(signum, _):
        if process.poll() is None:
            try:
                # Send signal to entire process group (includes uvicorn reloader)
                os.killpg(process.pid, signum)
                process.wait(timeout=1)
            except (ProcessLookupError, subprocess.TimeoutExpired, PermissionError):
                # Process group may already be gone, try direct kill
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        process.wait()
    except KeyboardInterrupt:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=1)
        except (ProcessLookupError, subprocess.TimeoutExpired, PermissionError):
            try:
                process.kill()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
    finally:
        os.close(master_fd)

    sys.exit(process.returncode if process.returncode is not None else 0)


# Assign the standalone function to the ServerMonitor class
ServerMonitor.read = monitor_read_standalone


if __name__ == "__main__":
    # Default to read mode when run directly
    ServerMonitor.read()
