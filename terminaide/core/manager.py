# terminaide/core/manager.py

"""
TTYd process management and lifecycle control.

This module is responsible for starting, monitoring, and stopping ttyd processes.
It ensures proper process cleanup and provides health monitoring capabilities.
The manager adapts its behavior based on whether we're using a single-script or
multi-script configuration, handling multiple ttyd processes when needed.
"""

import os
import sys
import socket
import time
import signal
import logging
import subprocess
import platform
from datetime import datetime
from typing import Optional, List, Dict, Any, Set, Tuple
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from ..exceptions import TTYDStartupError, TTYDProcessError, PortAllocationError
from ..installer import setup_ttyd
from .settings import TTYDConfig, ScriptConfig

logger = logging.getLogger("terminaide")


class TTYDManager:
    """
    Manages the lifecycle of ttyd processes.
    
    This class handles all aspects of ttyd processes, including:
    - Process startup and shutdown
    - Health monitoring
    - Resource cleanup
    - Signal handling
    - Port allocation for multiple processes
    
    It supports both single-script and multi-script configurations.
    """
    
    def __init__(self, config: TTYDConfig):
        """
        Initialize the TTYDManager.

        Args:
            config: TTYDConfig instance with process configuration
        """
        self.config = config
        self._ttyd_path: Optional[Path] = None
        self._setup_ttyd()
        
        # Track processes by route path
        self.processes: Dict[str, subprocess.Popen] = {}
        self.start_times: Dict[str, datetime] = {}
        
        # Handle port allocation
        self._base_port = config.port
        self._allocate_ports()

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
    
    def _allocate_ports(self) -> None:
        """
        Allocate ports for each script configuration.
        
        This method assigns a unique port to each script configuration,
        starting from the base port and incrementing for each script.
        It checks for port availability to avoid conflicts.
        """
        # Get configs without assigned ports
        configs_to_assign = [
            config for config in self.config.script_configs 
            if config.port is None
        ]
        
        # Get already assigned ports to avoid duplicates
        assigned_ports = {
            config.port for config in self.config.script_configs 
            if config.port is not None
        }
        
        # Start from base port for allocation
        next_port = self._base_port
        
        # Allocate ports to each config
        for config in configs_to_assign:
            # Find next available port
            while next_port in assigned_ports or self._is_port_in_use("127.0.0.1", next_port):
                next_port += 1
                
                # Avoid trying forever
                if next_port > 65000:
                    raise PortAllocationError("Failed to allocate ports: port range exhausted")
            
            # Assign the port
            config.port = next_port
            assigned_ports.add(next_port)
            next_port += 1
        
        # Log port assignments
        for config in self.config.script_configs:
            logger.info(f"Assigned port {config.port} to script at route {config.route_path}")

    def _build_command(self, script_config: ScriptConfig) -> List[str]:
        """
        Build the ttyd command with all necessary arguments for a script.
        
        This method constructs the command line arguments for ttyd based on
        the current configuration, taking into account both the global config
        and script-specific settings.
        
        Args:
            script_config: Script configuration to build command for
            
        Returns:
            List of command arguments for ttyd process
        """
        if not self._ttyd_path:
            raise TTYDStartupError("ttyd binary path not set")
            
        cmd = [str(self._ttyd_path)]
        
        # Basic configuration
        cmd.extend(['-p', str(script_config.port)])
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
            sys.executable,  # e.g. 'python'
            str(script_config.client_script)
        ])
        
        return cmd

    def _is_port_in_use(self, host: str, port: int) -> bool:
        """
        Check if a TCP port is in use on the given host.
        
        Args:
            host: Host address to check
            port: Port number to check
            
        Returns:
            True if something is listening, False otherwise
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((host, port)) == 0

    def _kill_process_on_port(self, host: str, port: int) -> None:
        """
        Attempt to kill whatever process is listening on the given port.
        
        This is a lightweight "best effort" approach, using lsof/fuser on Unix
        or other commands as needed. It won't work on Windows by default.
        
        Args:
            host: Host address where process is listening
            port: Port number where process is listening
        """
        system = platform.system().lower()
        logger.warning(
            f"Port {port} is already in use. Attempting to kill leftover process..."
        )

        try:
            if system in ["linux", "darwin"]:
                # lsof -t -i :port => returns PIDs
                # xargs kill -9 => kill them
                cmd = f"lsof -t -i tcp:{port}"
                # Use sudo if you want to ensure permission
                result = subprocess.run(
                    cmd.split(),
                    capture_output=True,
                    text=True
                )
                pids = result.stdout.strip().split()
                for pid in pids:
                    if pid.isdigit():
                        logger.warning(f"Killing leftover process {pid} on port {port}")
                        subprocess.run(["kill", "-9", pid], check=False)
            else:
                logger.warning("Automatic leftover kill not implemented on this OS.")
        except Exception as e:
            logger.error(f"Failed to kill leftover process on port {port}: {e}")

    def start(self) -> None:
        """
        Start all ttyd processes based on script configurations.
        
        This method launches ttyd processes for each script configuration and monitors
        their startup to ensure they're running correctly.

        Raises:
            TTYDStartupError: If any process fails to start
        """
        if not self.config.script_configs:
            raise TTYDStartupError("No script configurations found")
            
        logger.info(
            f"Starting {len(self.config.script_configs)} ttyd processes "
            f"({'multi-script' if self.config.is_multi_script else 'single-script'} mode)"
        )
        
        # Start each process
        for script_config in self.config.script_configs:
            self.start_process(script_config)

    def start_process(self, script_config: ScriptConfig) -> None:
        """
        Start a single ttyd process for a script configuration.
        
        Args:
            script_config: Script configuration to start
            
        Raises:
            TTYDStartupError: If process fails to start
            TTYDProcessError: If process is already running
        """
        route_path = script_config.route_path
        
        # Check if process already running for this route
        if route_path in self.processes and self.is_process_running(route_path):
            raise TTYDProcessError(f"TTYd process already running for route {route_path}")

        # --- CHECK AND KILL ANY LEFTOVER PROCESS ON THIS PORT ---
        host = self.config.ttyd_options.interface
        port = script_config.port
        
        if self._is_port_in_use(host, port):
            self._kill_process_on_port(host, port)
            # Let the OS finish killing
            time.sleep(1.0)
            # Double-check
            if self._is_port_in_use(host, port):
                raise TTYDStartupError(
                    f"Port {port} is still in use after attempting to kill leftover process."
                )

        cmd = self._build_command(script_config)
        cmd_str = ' '.join(cmd)
        logger.info(f"Starting ttyd for route {route_path} with command: {cmd_str}")

        try:
            # Start the process in a new session to isolate signals
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            
            # Track the process
            self.processes[route_path] = process
            self.start_times[route_path] = datetime.now()

            # Monitor startup with longer timeout in debug mode
            timeout = 4 if self.config.debug else 2
            check_interval = 0.1
            checks = int(timeout / check_interval)

            for _ in range(checks):
                if process.poll() is not None:
                    stderr = process.stderr.read().decode('utf-8')
                    logger.error(f"ttyd failed to start for route {route_path}. Error: {stderr}")
                    # Clean up
                    self.processes.pop(route_path, None)
                    self.start_times.pop(route_path, None)
                    raise TTYDStartupError(stderr=stderr)
                    
                if self.is_process_running(route_path):
                    logger.info(
                        f"ttyd process started successfully for route {route_path} "
                        f"with PID {process.pid} on port {port}"
                    )
                    return
                    
                time.sleep(check_interval)
                
            logger.error(f"ttyd process for route {route_path} did not start within timeout")
            # Clean up
            self.processes.pop(route_path, None)
            self.start_times.pop(route_path, None) 
            raise TTYDStartupError(f"ttyd process for route {route_path} did not start within timeout")

        except subprocess.SubprocessError as e:
            logger.error(f"Failed to start ttyd for route {route_path}: {e}")
            raise TTYDStartupError(str(e))

    def stop(self) -> None:
        """
        Stop all ttyd processes if they're running.
        
        This method ensures clean process termination of all processes,
        using SIGTERM first, followed by SIGKILL if necessary.
        """
        logger.info(f"Stopping all ttyd processes ({len(self.processes)} total)")
            
        # Make a copy of keys to avoid modification during iteration
        for route_path in list(self.processes.keys()):
            self.stop_process(route_path)
            
        # Clear tracking dictionaries
        self.processes.clear()
        self.start_times.clear()
            
        logger.info("All ttyd processes stopped successfully")

    def stop_process(self, route_path: str) -> None:
        """
        Stop a specific ttyd process if it's running.
        
        Args:
            route_path: Route path of the process to stop
        """
        process = self.processes.get(route_path)
        if not process:
            return
            
        logger.info(f"Stopping ttyd process for route {route_path}...")
        
        try:
            # Try graceful shutdown first
            if os.name == 'nt':  # Windows
                process.terminate()
            else:  # Unix-like
                try:
                    pgid = os.getpgid(process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    # Process is already gone, which is fine
                    pass

            try:
                process.wait(timeout=5)  # Wait up to 5 seconds
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown fails
                if os.name == 'nt':
                    process.kill()
                else:
                    try:
                        pgid = os.getpgid(process.pid)
                        os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError:
                        # Process is already gone, which is fine
                        pass
                
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    # If we still can't wait, the process is probably gone or stuck
                    pass

        except Exception as e:
            logger.warning(f"Error during process cleanup for route {route_path}: {e}")
        
        # Clean up tracking
        self.processes.pop(route_path, None)
        self.start_times.pop(route_path, None)
        logger.info(f"ttyd process for route {route_path} stopped successfully")

    def is_process_running(self, route_path: str) -> bool:
        """
        Check if ttyd process for a specific route is currently running.
        
        Args:
            route_path: Route path to check
            
        Returns:
            True if process exists and is running
        """
        process = self.processes.get(route_path)
        return bool(process and process.poll() is None)

    def get_process_uptime(self, route_path: str) -> Optional[float]:
        """
        Get process uptime in seconds for a specific route.
        
        Args:
            route_path: Route path to check
            
        Returns:
            Uptime in seconds or None if process is not running
        """
        if self.is_process_running(route_path) and route_path in self.start_times:
            return (datetime.now() - self.start_times[route_path]).total_seconds()
        return None

    def check_health(self) -> Dict[str, Any]:
        """
        Get comprehensive health check information about all processes.
        
        Returns:
            Dictionary containing process status, uptime, and configuration details
        """
        processes_health = []
        
        for config in self.config.script_configs:
            route_path = config.route_path
            is_running = self.is_process_running(route_path)
            
            process_info = {
                "route_path": route_path,
                "script": str(config.client_script),
                "status": "running" if is_running else "stopped",
                "uptime": self.get_process_uptime(route_path),
                "port": config.port,
                "pid": self.processes.get(route_path).pid if is_running else None,
                "title": config.title or self.config.title
            }
            
            processes_health.append(process_info)
            
        return {
            "processes": processes_health,
            "ttyd_path": str(self._ttyd_path) if self._ttyd_path else None,
            "is_multi_script": self.config.is_multi_script,
            "process_count": len(self.processes),
            "mounting": "root" if self.config.is_root_mounted else "non-root",
            **self.config.get_health_check_info()
        }
    
    def restart_process(self, route_path: str) -> None:
        """
        Restart a specific ttyd process.
        
        Args:
            route_path: Route path of the process to restart
            
        Raises:
            TTYDStartupError: If process fails to start
        """
        logger.info(f"Restarting ttyd process for route {route_path}")
        
        # Find the matching script config
        script_config = None
        for config in self.config.script_configs:
            if config.route_path == route_path:
                script_config = config
                break
                
        if not script_config:
            raise TTYDStartupError(f"No script configuration found for route {route_path}")
        
        # Stop the existing process
        self.stop_process(route_path)
        
        # Start a new process
        self.start_process(script_config)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        """
        Manage ttyd processes lifecycle within FastAPI application.
        
        This context manager ensures proper startup and cleanup of all ttyd
        processes during the application lifecycle.
        
        Usage:
            app = FastAPI(lifespan=manager.lifespan)
        """
        try:
            self.start()
            yield
        finally:
            self.stop()