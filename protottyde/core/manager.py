# protottyde/core/manager.py

"""
TTYd process management and lifecycle control.

This module is responsible for starting, monitoring, and stopping the ttyd process.
It ensures proper process cleanup and provides health monitoring capabilities.
The manager adapts its behavior based on whether we're using root or non-root
mounting configurations.
"""

import os
import signal
import logging
import subprocess
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from ..exceptions import TTYDStartupError, TTYDProcessError
from ..installer import setup_ttyd
from .settings import TTYDConfig

logger = logging.getLogger("protottyde")

class TTYDManager:
    """
    Manages the lifecycle of the ttyd process.
    
    This class handles all aspects of the ttyd process, including:
    - Process startup and shutdown
    - Health monitoring
    - Resource cleanup
    - Signal handling
    """
    
    def __init__(self, config: TTYDConfig):
        """
        Initialize the TTYDManager.

        Args:
            config: TTYDConfig instance with process configuration
        """
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self._start_time: Optional[datetime] = None
        self._ttyd_path: Optional[Path] = None
        self._setup_ttyd()

    def _setup_ttyd(self) -> None:
        """
        Set up ttyd binary and verify it's ready to use.
        
        This method handles the installation and verification of the ttyd binary,
        using our installer module to manage platform-specific binaries.
        """
        try:
            self._ttyd_path = setup_ttyd()
            logger.info(f"Using ttyd binary at: {self._ttyd_path}")
        except Exception as e:
            logger.error(f"Failed to set up ttyd: {e}")
            raise TTYDStartupError(f"Failed to set up ttyd: {e}")

    def _build_command(self) -> List[str]:
        """
        Build the ttyd command with all necessary arguments.
        
        This method constructs the command line arguments for ttyd based on
        the current configuration, taking into account both root and non-root
        mounting scenarios.
        
        Returns:
            List of command arguments for ttyd process
        """
        if not self._ttyd_path:
            raise TTYDStartupError("ttyd binary path not set")
            
        cmd = [str(self._ttyd_path)]
        
        # Basic configuration
        cmd.extend(['-p', str(self.config.port)])
        cmd.extend(['-i', self.config.ttyd_options.interface])
        
        # Security settings
        if not self.config.ttyd_options.check_origin:
            cmd.append('--no-check-origin')
        
        if self.config.ttyd_options.credential_required:
            if not (self.config.ttyd_options.username and self.config.ttyd_options.password):
                raise TTYDStartupError("Credentials required but not provided")
            cmd.extend([
                '-c', 
                f"{self.config.ttyd_options.username}:{self.config.ttyd_options.password}"
            ])
        
        # Debug mode settings
        if self.config.debug:
            cmd.extend(['-d', '3'])  # Maximum debug output
        
        # Terminal customization
        theme_json = self.config.theme.model_dump_json()
        cmd.extend(['-t', f'theme={theme_json}'])
        
        # Explicitly set writable or read-only mode
        if self.config.ttyd_options.writable:
            cmd.append('--writable')
        else:
            cmd.append('-R')
        
        # Add client script to run in the terminal
        cmd.extend([
            'python',
            str(self.config.client_script)
        ])
        
        return cmd

    def start(self) -> None:
        """
        Start the ttyd process with the current configuration.
        
        This method launches ttyd with appropriate settings and monitors
        its startup to ensure it's running correctly.

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
            # Start the process in a new session to isolate signals
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            self._start_time = datetime.now()

            # Monitor startup with longer timeout in debug mode
            timeout = 4 if self.config.debug else 2
            check_interval = 0.1
            checks = int(timeout / check_interval)

            for _ in range(checks):
                if self.process.poll() is not None:
                    stderr = self.process.stderr.read().decode('utf-8')
                    logger.error(f"ttyd failed to start. Error: {stderr}")
                    raise TTYDStartupError(stderr=stderr)
                    
                if self.is_running:
                    mount_type = "root" if self.config.is_root_mounted else "non-root"
                    logger.info(
                        f"ttyd process started successfully with PID {self.process.pid} "
                        f"({mount_type} mounting)"
                    )
                    return
                    
                import time
                time.sleep(check_interval)
                
            logger.error("ttyd process did not start within timeout")
            raise TTYDStartupError("ttyd process did not start within timeout")

        except subprocess.SubprocessError as e:
            logger.error(f"Failed to start ttyd: {e}")
            raise TTYDStartupError(str(e))

    def stop(self) -> None:
        """
        Stop the ttyd process if it's running.
        
        This method ensures clean process termination using SIGTERM first,
        followed by SIGKILL if necessary.
        """
        if self.process:
            logger.info("Stopping ttyd process...")
            
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
            logger.info("ttyd process stopped successfully")

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

    def check_health(self) -> Dict[str, Any]:
        """
        Get comprehensive health check information about the process.
        
        Returns:
            Dictionary containing process status, uptime, and configuration details
        """
        return {
            "status": "running" if self.is_running else "stopped",
            "uptime": self.uptime,
            "pid": self.process.pid if self.process else None,
            "mounting": "root" if self.config.is_root_mounted else "non-root",
            "terminal_path": self.config.terminal_path,
            "ttyd_path": str(self._ttyd_path) if self._ttyd_path else None,
            **self.config.get_health_check_info()
        }

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        """
        Manage ttyd process lifecycle within FastAPI application.
        
        This context manager ensures proper startup and cleanup of the ttyd
        process during the application lifecycle.
        
        Usage:
            app = FastAPI(lifespan=manager.lifespan)
        """
        try:
            self.start()
            yield
        finally:
            self.stop()