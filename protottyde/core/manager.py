# protottyde/core/manager.py

"""
TTYd process management and lifecycle control.
"""

import os
import signal
import logging
import subprocess
import shutil
from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI
from ..exceptions import TTYDNotFoundError, TTYDStartupError, TTYDProcessError
from .settings import TTYDConfig

logger = logging.getLogger("protottyde")

class TTYDManager:
    """Manages the lifecycle of the ttyd process."""
    
    def __init__(self, config: TTYDConfig):
        """
        Initialize the TTYDManager.

        Args:
            config: TTYDConfig instance with process configuration
        
        Raises:
            TTYDNotFoundError: If ttyd is not installed
        """
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self._start_time: Optional[datetime] = None
        self._verify_ttyd_installed()

    def _verify_ttyd_installed(self) -> None:
        """Verify ttyd is installed and accessible."""
        if not shutil.which('ttyd'):
            raise TTYDNotFoundError()

    def _build_command(self) -> List[str]:
        """Build the ttyd command with all arguments."""
        cmd = ['ttyd']
        cmd.extend(self.config.to_ttyd_args())
        cmd.extend([
            'python',
            str(self.config.client_script)
        ])
        return cmd

    def start(self) -> None:
        """
        Start the ttyd process.

        Raises:
            TTYDStartupError: If process fails to start
            TTYDProcessError: If process is already running
        """
        if self.is_running:
            raise TTYDProcessError("TTYd process is already running")

        cmd = self._build_command()
        cmd_str = ' '.join(cmd)
        logger.info(f"Starting ttyd with command: {cmd_str}")

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True  # Prevent signal propagation
            )
            self._start_time = datetime.now()

            # Check immediate failure
            for _ in range(10):  # Wait up to 1 second for startup
                if self.process.poll() is not None:
                    stderr = self.process.stderr.read().decode('utf-8')
                    logger.error(f"ttyd failed to start. Error: {stderr}")
                    raise TTYDStartupError(stderr=stderr)
                if self.is_running:
                    logger.info("ttyd process started successfully")
                    return
                import time
                time.sleep(0.1)
                
            raise TTYDStartupError("ttyd process did not start within timeout")

        except subprocess.SubprocessError as e:
            logger.error(f"Failed to start ttyd: {e}")
            raise TTYDStartupError(str(e))

    def stop(self) -> None:
        """Stop the ttyd process if running."""
        if self.process:
            logger.debug("Stopping ttyd process")
            
            # Try graceful shutdown first
            if os.name == 'nt':  # Windows
                self.process.terminate()
            else:  # Unix-like
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)

            try:
                self.process.wait(timeout=5)  # Wait up to 5 seconds
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown fails
                if os.name == 'nt':
                    self.process.kill()
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                self.process.wait()

            self.process = None
            self._start_time = None

    @property
    def is_running(self) -> bool:
        """Check if ttyd process is currently running."""
        return bool(self.process and self.process.poll() is None)

    @property
    def uptime(self) -> Optional[float]:
        """Get process uptime in seconds, if running."""
        if self._start_time and self.is_running:
            return (datetime.now() - self._start_time).total_seconds()
        return None

    def check_health(self) -> dict:
        """Get health check information about the process."""
        return {
            "status": "running" if self.is_running else "stopped",
            "uptime": self.uptime,
            "pid": self.process.pid if self.process else None,
            **self.config.get_health_check_info()
        }

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        """
        Manage ttyd process lifecycle within FastAPI application.
        
        Usage:
            app = FastAPI(lifespan=manager.lifespan)
        """
        try:
            self.start()
            yield
        finally:
            self.stop()