# terminaide/demo/client.py

"""
Default client script for terminaide.

This script is used as the default client when no client_script
is provided to the serve_tty function. It runs the same demo
that is available through the explicit demo.run() interface.
"""

from .snake import run_demo

if __name__ == "__main__":
    run_demo()