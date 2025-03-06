#!/usr/bin/env python3
# tests/client_1.py

"""
Sample terminal client for terminaide multi-script testing.
This client implements a simple quote guessing game.
"""

import random
import time
import sys
import os
from typing import List, Tuple

# ASCII Art Header
HEADER = """
╔═════════════════════════════════════════════╗
║                QUOTE GUESSER                ║
║         Guess the author of the quote!      ║
╚═════════════════════════════════════════════╝
"""

# Game quotes with authors
QUOTES: List[Tuple[str, str]] = [
    ("Be yourself; everyone else is already taken.", "Oscar Wilde"),
    ("Two things are infinite: the universe and human stupidity; and I'm not sure about the universe.", "Albert Einstein"),
    ("So many books, so little time.", "Frank Zappa"),
    ("Be the change that you wish to see in the world.", "Mahatma Gandhi"),
    ("In three words I can sum up everything I've learned about life: it goes on.", "Robert Frost"),
    ("If you tell the truth, you don't have to remember anything.", "Mark Twain"),
    ("A friend is someone who knows all about you and still loves you.", "Elbert Hubbard"),
    ("Always forgive your enemies; nothing annoys them so much.", "Oscar Wilde"),
    ("Live as if you were to die tomorrow. Learn as if you were to live forever.", "Mahatma Gandhi"),
    ("Without music, life would be a mistake.", "Friedrich Nietzsche")
]

def clear_screen() -> None:
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_with_delay(text: str, delay: float = 0.03) -> None:
    """Print text with a typing effect."""
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write('\n')

def get_random_quote() -> Tuple[str, str]:
    """Return a random quote and its author."""
    return random.choice(QUOTES)

def play_round() -> bool:
    """Play a single round of the quote guessing game."""
    quote, author = get_random_quote()
    
    print_with_delay(f"\nHere's the quote:")
    print(f"\n\033[1;36m'{quote}'\033[0m\n")
    
    print("Who said this? (Type your guess or 'q' to quit)")
    
    guess = input("> ").strip()
    
    if guess.lower() == 'q':
        return False
    
    if guess.lower() == author.lower():
        print("\n\033[1;32mCorrect! Well done!\033[0m")
    else:
        print(f"\n\033[1;31mNot quite. The correct answer is: {author}\033[0m")
    
    return True

def main() -> None:
    """Main game loop."""
    clear_screen()
    print(HEADER)
    
    print_with_delay("Welcome to Quote Guesser!", 0.05)
    print_with_delay("I'll show you a famous quote, and you try to guess who said it.", 0.03)
    print_with_delay("Type 'q' at any time to quit.", 0.03)
    
    print("\nPress Enter to start!")
    input()
    
    keep_playing = True
    while keep_playing:
        clear_screen()
        print(HEADER)
        keep_playing = play_round()
        
        if keep_playing:
            print("\nPress Enter for the next quote, or 'q' to quit.")
            response = input("> ").strip()
            if response.lower() == 'q':
                keep_playing = False
    
    print_with_delay("\nThanks for playing Quote Guesser! Goodbye!", 0.05)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nGame interrupted. Goodbye!")
        sys.exit(0)