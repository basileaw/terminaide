# script.py
"""
Terminaide Script Server Demo

This demonstrates using serve_script() to serve another Python script
through a terminal in the browser.
"""

from terminaide import serve_script

serve_script("terminarcade_demo.py", port=8000, title="Terminarcade Demo")
