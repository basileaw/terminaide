# test-server/main.py

import os
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from protottyde import serve_tty

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize app
app = FastAPI()

# Configure ttyd
is_container = os.getenv('IS_CONTAINER', 'false').lower() == 'true'
server_port = int(os.getenv('PORT', '80' if is_container else '8000'))
ttyd_port = int(os.getenv('TTYD_PORT', '7681'))  # Default ttyd port

# Redirect root to terminal
@app.get("/")
async def root():
    return RedirectResponse(url="/ttyd")

# Set up the terminal service
client_script = Path(__file__).parent / "client" / "main.py"
serve_tty(
    app,
    client_script=client_script,
    mount_path="/ttyd",
    port=ttyd_port,  # Specify ttyd port explicitly
    theme={"background": "black"},
    debug=not is_container
)

if __name__ == '__main__':
    import uvicorn
    
    uvicorn_config = {
        "app": "main:app",
        "host": "0.0.0.0",
        "port": server_port,
        "log_level": "info"
    }
    
    # Add reload in development
    if not is_container:
        uvicorn_config.update({
            "reload": True,
            "reload_dirs": ["./"]
        })

    uvicorn.run(**uvicorn_config)