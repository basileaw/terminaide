# client.py
import time
import os
import sys

def main():
    print("Simple Terminaide Client")
    print("-----------------------")
    print(f"Working directory: {os.getcwd()}")
    print(f"Script location: {os.path.abspath(__file__)}")
    print(f"Python version: {sys.version}")
    print("-----------------------")
    
    counter = 0
    try:
        while True:
            counter += 1
            print(f"Hello from terminaide! Counter: {counter}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting gracefully...")

if __name__ == "__main__":
    main()