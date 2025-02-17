# client.py

import argparse
from chatline import Interface

# Example messages for our test client implementation
MESSAGES = {
    "system": (
        'Write in present tense. Write in third person. Use the following text styles:\n'
        '- "quotes" for dialogue\n'
        '- [Brackets...] for actions\n'
        '- underscores for emphasis\n'
        '- asterisks for bold text'
    ),
    "user": (
        """Write the line: "[The machine powers on and hums...]\n\n"""
        """Then, start a new, 25-word paragraph."""
        """Begin with a greeting from the machine itself: " "Hey there," " """
    )
}

def main():
    parser = argparse.ArgumentParser(description='ChatLine Interface')
    parser.add_argument('-e', '--endpoint',
        help='Remote endpoint URL for chat service')
    parser.add_argument('--enable-logging',
        action='store_true',
        help='Enable debug logging')
    parser.add_argument('--log-file',
        help='Log file path (use "-" for stdout)')
    
    args = parser.parse_args()
    
    chat = Interface(
        endpoint=args.endpoint, 
        logging_enabled=args.enable_logging,
        log_file=args.log_file
    )
    
    chat.preface("Welcome to ChatLine", title="Baze, Inc.", border_color="dim yellow")
    chat.start(MESSAGES)

if __name__ == "__main__":
    main()