# ttyd_manager.py 

import json
import logging
import subprocess
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from pathlib import Path

logger = logging.getLogger("uvicorn")

class TTYDManager:
    def __init__(self, port: int = 7681, theme: Optional[Dict[str, Any]] = None):
        self.port = port
        self.theme = theme or {"background": "black"}
        self.process: Optional[subprocess.Popen] = None
        self.client_path = Path(__file__).parent.parent / "client" / "main.py"

    def start(self):
        """Start the ttyd process"""
        if self.process:  # Kill existing process if it exists
            self.stop()

        self.process = subprocess.Popen(
            ['ttyd',
             '--writable',
             '-p', str(self.port),
             '-t', 'cursorStyle=block',
             '-t', 'cursorBlink=true',
             '-t', f'theme={json.dumps(self.theme)}',
             'python',
             str(self.client_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        logger.info(f"Started ttyd process on port {self.port}")

    def stop(self):
        """Stop the ttyd process"""
        if self.process:
            logger.info("Cleaning up ttyd process...")
            self.process.terminate()
            self.process.wait()
            self.process = None

    @property
    def is_running(self) -> bool:
        """Check if ttyd process is running"""
        return self.process is not None and self.process.poll() is None

    @asynccontextmanager
    async def lifespan(self, app=None):
        """Manage the ttyd process lifecycle"""
        self.start()
        try:
            yield
        finally:
            self.stop()