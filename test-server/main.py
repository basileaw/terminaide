# backend/server.py

import os
import sys
import signal
import uvicorn
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from modules.ttyd_manager import TTYDManager
from modules.proxy import ProxyManager, setup_proxy_routes

logger = logging.getLogger("uvicorn")

# Initialize app and managers
ttyd_manager = TTYDManager()
proxy_manager = ProxyManager("127.0.0.1", 7681)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with ttyd_manager.lifespan(app):
        try:
            yield
        finally:
            await proxy_manager.cleanup()

app = FastAPI(lifespan=lifespan)

# Setup static files and templates
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
setup_proxy_routes(app, proxy_manager)

@app.get("/health")
def health_check():
    return {"status": "ok", "ttyd_running": ttyd_manager.is_running}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        host = request.headers.get('host', '').split(':')[0]
        logger.info(f'Using host: {host}')
        return templates.TemplateResponse("index.html", {
            "request": request,
            "host": host,
            "ttyd_path": "/ttyd/",
            "background_color": ttyd_manager.theme["background"]
        })
    except Exception as e:
        logger.error(f'Error in index route: {e}')
        return str(e)

if __name__ == '__main__':
    # Handle shutdown gracefully
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda s, f: (ttyd_manager.stop(), sys.exit(0)))
    
    # Configure server
    is_container = os.getenv('IS_CONTAINER', 'false').lower() == 'true'
    uvicorn_args = {
    "app": "main:app",  # Changed from "server:app"
    "host": "0.0.0.0",
    "port": int(os.getenv('PORT', '80' if is_container else '8000')),
    **({"reload": True, "reload_dirs": ["./"]} if not is_container else {})
    }

    try:
        logger.info(f"Starting server on port {uvicorn_args['port']}")
        uvicorn.run(**uvicorn_args)
    finally:
        ttyd_manager.stop()