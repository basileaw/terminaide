# server.py
import os
from pathlib import Path
from fastapi import FastAPI
from terminaide import serve_terminal

app = FastAPI()

serve_terminal(app, client_script="client.py")

# Print some debug info to help troubleshoot path issues
print(f"Current working directory: {os.getcwd()}")
print(f"Server script location: {os.path.abspath(__file__)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)