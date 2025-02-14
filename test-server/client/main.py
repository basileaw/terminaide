import bs4
import json
import random
import requests
import readline
import sys
import os

from rich.text import Text
from rich.panel import Panel
from rich.padding import Padding
from rich.console import Console, Group
from rich.live import Live
from rich.layout import Layout

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def hide_cursor():
    if os.name == 'posix':
        sys.stdout.write('\033[?25l')
        sys.stdout.flush()

def show_cursor():
    if os.name == 'posix':
        sys.stdout.write('\033[?25h')
        sys.stdout.flush()

def get_single_keypress():
    """Get a single keypress without requiring Enter"""
    if os.name == 'nt':  # For Windows
        import msvcrt
        return msvcrt.getch().decode().lower()
    else:  # For Unix-like systems
        import tty
        import termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1).lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

def create_question_panel(quote_text, round_num, console_width):
    """Create a panel for the current question"""
    return Panel(
        Group(
            Text("Who said the following quote?\n"),
            Text(quote_text, style="bold")
        ),
        title=f"ROUND {round_num}",
        border_style="bold blue",
        title_align="left",
        padding=1,
        width=console_width - 2
    )

class Padded_Console(Console):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_question_panel = None
        # Initialize with header
        clear_screen()
        self.print_header()

    def create_header(self):
        return Panel(
            "Quote Guessing Game",
            border_style="bold cyan",
            padding=1,
            width=self.width - 2
        )

    def print_header(self):
        """Print the header panel"""
        super().print(self.create_header(), justify="center")

    def set_question_panel(self, panel):
        """Set the current question panel to be displayed"""
        self.current_question_panel = panel
        if panel is not None:
            clear_screen()
            self.print_header()
            super().print(panel, justify="center")

    def show_end_round(self, result_panel):
        """Display end of round state with header, question, and result"""
        clear_screen()
        self.print_header()
        if self.current_question_panel:
            super().print(self.current_question_panel, justify="center")
        super().print(result_panel, justify="center")

    def print(self, *args, padding=(1, 0, 1, 0), clear=False, **kwargs):
        """
        Prints content while maintaining header
        """
        if clear:
            clear_screen()
            self.print_header()
            if self.current_question_panel:
                super().print(self.current_question_panel, justify="center")
            
        if args and args[0] is not None:
            content = Padding(args[0], padding)
            super().print(content, **kwargs)

console = Padded_Console(log_time=None)

# Hide cursor at start
hide_cursor()

try:
    base_url = "http://quotes.toscrape.com"
    url = base_url
    all_quotes = []

    console.print("Scraping quotes from web...", style="italic dim", justify="center", width=console.width)
    while url:
        # Get the current page
        quotes = requests.get(url)
        quotes_soup = bs4.BeautifulSoup(quotes.text, "html.parser")
        quotes_list = quotes_soup.select(".quote")

        # Process quotes from current page
        for quote in quotes_list:
            text = quote.select(".text")[0].get_text()
            author = quote.select(".author")[0].get_text()
            author_link = quote.select("a")[0]["href"]

            quote_dict = {
                "text": text,
                "author": author,
                "href": base_url + author_link
            }
            all_quotes.append(quote_dict)

        # Look for next page button
        next_btn = quotes_soup.select(".next a")
        if next_btn:
            next_page = next_btn[0]["href"]
            url = base_url + next_page
        else:
            url = None

    playing = True
    round = 0

    while playing:
        round += 1
        guessing = True
        guess = ""
        guesses = 4
        random_quote = random.choice(all_quotes)

        # Set the question panel for this round
        question_panel = create_question_panel(random_quote["text"], round, console.width)
        console.set_question_panel(question_panel)

        while guessing:
            while guess.lower() != random_quote["author"].lower() and guesses > 0:
                show_cursor()
                guess = input("> ")
                hide_cursor()
                
                if guess == "":
                    show_cursor()
                    quit()

                guesses -= 1
                if guess.lower() == random_quote["author"].lower():
                    result_panel = Panel(
                        f"You nailed it! The correct answer is indeed [bold underline]{random_quote['author']}[/bold underline]",
                        title=f"YOU WIN",
                        border_style="bold green",
                        title_align="left",
                        padding=1,
                        width=console.width - 2
                    )
                    console.show_end_round(result_panel)
                    guessing = False
                    break

                elif guesses == 3:
                    res = requests.get(random_quote["href"])
                    soup = bs4.BeautifulSoup(res.text, "html.parser")
                    birth_date = soup.select(".author-born-date")[0].get_text()
                    birth_place = soup.select(".author-born-location")[0].get_text()
                    console.print(
                        f"[bold red]Nope![/bold red]\n\nHere's a hint: The author was born on {birth_date} {birth_place}",
                        justify="center",
                        width=console.width
                    )

                elif guesses == 2:
                    console.print(
                        f"[bold red]Wrong Again![/bold red]\n\nHere's another hint: The author's first name starts with: {random_quote['author'][0]}",
                        justify="center",
                        width=console.width
                    )

                elif guesses == 1:
                    last_initial = random_quote['author'].split(" ")[-1][0]
                    console.print(
                        f"[bold red]YOUR'RE STILL WRONG![/bold red]\n\nHere's your last hint: The author's last name starts with: {last_initial}",
                        justify="center",
                        width=console.width
                    )

                else:
                    result_panel = Panel(
                        f"Sorry buddy, the correct answer is actually [bold underline]{random_quote['author']}[/bold underline]",
                        title=f"YOU LOSE",
                        border_style="bold red",
                        title_align="left",
                        padding=1,
                        width=console.width - 2
                    )
                    console.show_end_round(result_panel)
                    guessing = False
                    break

        # Keep panels visible and add play again prompt
        console.print(
            "Would you like to play again (y/n)?",
            justify="center",
            width=console.width
        )
        
        # Get single keypress
        play_again = get_single_keypress()
        
        if play_again == 'y':
            playing = True
        else:
            playing = False
            hide_cursor()
            clear_screen()  # Clear everything before showing goodbye
            console.print(
                Panel(
                    "Thanks for playing! See you next time!",
                    border_style="bold magenta",
                    padding=1,
                    width=console.width - 2
                ),
                justify="center"
            )
            while True:
                try:
                    get_single_keypress()
                except:
                    break

finally:
    # We'll never reach this now, but keep it as a safety net
    show_cursor()