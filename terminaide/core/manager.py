# core/manager.py

""" Manages TTYd processes for single (solo-server) or multi-terminal (apps-server) setups, ensuring their lifecycle, cleanup, and health monitoring. """

import os
import sys
import socket
import time
import signal
import subprocess
import platform
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from .exceptions import TTYDStartupError, TTYDProcessError, PortAllocationError
from .ttyd_installer import setup_ttyd
from .data_models import TTYDConfig, ScriptConfig

logger = logging.getLogger("terminaide")

class TTYDManager:
    """ Manages the lifecycle of ttyd processes, including startup, shutdown, health checks, resource cleanup, and port allocation. Supports single (solo-server) or multi-terminal (apps-server) configurations. """

    def __init__(self, config: TTYDConfig, force_reinstall_ttyd: bool = None):
        """
        Initialize TTYDManager with the given TTYDConfig.
        
        Args:
            config: The TTYDConfig object
            force_reinstall_ttyd: If True, force reinstall ttyd even if it exists
        """
        self.config = config
        self._ttyd_path: Optional[Path] = None
        self._setup_ttyd(force_reinstall_ttyd)
        
        # Track processes by route
        self.processes: Dict[str, subprocess.Popen] = {}
        self.start_times: Dict[str, datetime] = {}
        
        # Base port handling
        self._base_port = config.port
        self._allocate_ports()

    def _setup_ttyd(self, force_reinstall: bool = None) -> None:
        """
        Set up and verify the ttyd binary.
        
        Args:
            force_reinstall: If True, force reinstall ttyd even if it exists
        """
        try:
            self._ttyd_path = setup_ttyd(force_reinstall)
            logger.debug(f"Using ttyd binary at: {self._ttyd_path}")
        except Exception as e:
            logger.error(f"Failed to set up ttyd: {e}")
            raise TTYDStartupError(f"Failed to set up ttyd: {e}")

    def _allocate_ports(self) -> None:
        """
        Allocate and validate ports for each script configuration.
        """
        configs_to_assign = [
            c for c in self.config.script_configs if c.port is None
        ]
        assigned_ports = {
            c.port for c in self.config.script_configs if c.port is not None
        }
        next_port = self._base_port
        
        # Track newly assigned ports
        new_assignments = []
        
        for cfg in configs_to_assign:
            while (next_port in assigned_ports
                   or self._is_port_in_use("127.0.0.1", next_port)):
                next_port += 1
                if next_port > 65000:
                    raise PortAllocationError("Port range exhausted")
            cfg.port = next_port
            assigned_ports.add(next_port)
            new_assignments.append((cfg.route_path, next_port))
            next_port += 1

        # Log all port assignments in a single message
        if new_assignments:
            assignments_str = ", ".join([f"{route}:{port}" for route, port in new_assignments])
            logger.debug(f"Port assignments: {assignments_str}")

    def _build_command(self, script_config: ScriptConfig) -> List[str]:
        """
        Construct the ttyd command using global and script-specific configs.
        """
        if not self._ttyd_path:
            raise TTYDStartupError("ttyd binary path not set")
            
        cmd = [str(self._ttyd_path)]
        cmd.extend(['-p', str(script_config.port)])
        cmd.extend(['-i', self.config.ttyd_options.interface])
        
        if not self.config.ttyd_options.check_origin:
            cmd.append('--no-check-origin')
        
        if self.config.ttyd_options.credential_required:
            if not (self.config.ttyd_options.username and self.config.ttyd_options.password):
                raise TTYDStartupError("Credentials required but not provided")
            cmd.extend([
                '-c',
                f"{self.config.ttyd_options.username}:{self.config.ttyd_options.password}"
            ])
        
        if self.config.debug:
            cmd.extend(['-d', '3'])

        theme_json = self.config.theme.model_dump_json()
        cmd.extend(['-t', f'theme={theme_json}'])
        
        cmd.extend(['-t', 'cursorInactiveStyle=none'])
        cmd.extend(['-t', 'cursorWidth=0'])
        cmd.extend(['-t', 'cursorBlink=True'])

        if self.config.ttyd_options.writable:
            cmd.append('--writable')
        else:
            cmd.append('-R')
        
        # Find the cursor_manager.py path
        cursor_manager_path = Path(__file__).parent / "cursor_manager.py"
        
        # Check if cursor management is enabled via environment variable
        cursor_mgmt_enabled = os.environ.get("TERMINAIDE_CURSOR_MGMT", "1").lower() in ("1", "true", "yes", "enabled")
        
        # Use cursor manager if it exists and is enabled
        if cursor_mgmt_enabled and cursor_manager_path.exists():
            logger.debug(f"Using cursor manager for script: {script_config.client_script}")
            python_cmd = [sys.executable, str(cursor_manager_path), str(script_config.client_script)]
        else:
            if cursor_mgmt_enabled and not cursor_manager_path.exists():
                logger.warning(f"Cursor manager not found at {cursor_manager_path}, using direct execution")
            python_cmd = [sys.executable, str(script_config.client_script)]
            
        if script_config.args:
            python_cmd.extend(script_config.args)
            
        cmd.extend(python_cmd)
        return cmd

    def _is_port_in_use(self, host: str, port: int) -> bool:
        """
        Check if a TCP port is in use on the given host.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((host, port)) == 0

    def _kill_process_on_port(self, host: str, port: int) -> None:
        """
        Attempt to kill any process listening on the given port, if supported.
        """
        system = platform.system().lower()
        logger.warning(f"Port {port} is in use. Attempting to kill leftover process...")

        try:
            if system in ["linux", "darwin"]:
                result = subprocess.run(
                    f"lsof -t -i tcp:{port}".split(),
                    capture_output=True,
                    text=True
                )
                pids = result.stdout.strip().split()
                for pid in pids:
                    if pid.isdigit():
                        logger.warning(f"Killing leftover process {pid} on port {port}")
                        subprocess.run(["kill", "-9", pid], check=False)
            else:
                logger.warning("Automatic kill not implemented on this OS.")
        except Exception as e:
            logger.error(f"Failed to kill leftover process on port {port}: {e}")

    def start(self) -> None:
        """
        Start all ttyd processes for each configured script.
        """
        if not self.config.script_configs:
            raise TTYDStartupError("No script configurations found")
            
        script_count = len(self.config.script_configs)
        mode_type = 'apps-server' if self.config.is_multi_script else 'solo-server'
        entry_mode = getattr(self.config, '_mode', 'script')
        logger.info(f"Starting {script_count} ttyd processes ({mode_type} mode via {entry_mode} API)")
        
        success_count = 0
        for script_config in self.config.script_configs:
            try:
                self.start_process(script_config)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to start process for {script_config.route_path}: {e}")
        
        logger.info(f"Started {success_count}/{script_count} processes successfully")

    def start_process(self, script_config: ScriptConfig) -> None:
        """
        Launch a single ttyd process for the given script config.
        """
        route_path = script_config.route_path
        if route_path in self.processes and self.is_process_running(route_path):
            raise TTYDProcessError(f"TTYd already running for route {route_path}")

        host = self.config.ttyd_options.interface
        port = script_config.port
        
        if self._is_port_in_use(host, port):
            self._kill_process_on_port(host, port)
            time.sleep(1.0)
            if self._is_port_in_use(host, port):
                raise TTYDStartupError(
                    f"Port {port} is still in use after trying to kill leftover process."
                )

        cmd = self._build_command(script_config)
        
        # Log detailed command at debug level only
        logger.debug(f"Process command for {route_path}: {' '.join(cmd)}")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            self.processes[route_path] = process
            self.start_times[route_path] = datetime.now()

            timeout = 4 if self.config.debug else 2
            check_interval = 0.1
            checks = int(timeout / check_interval)

            for _ in range(checks):
                if process.poll() is not None:
                    stderr = process.stderr.read().decode('utf-8')
                    logger.error(f"ttyd failed to start for route {route_path}: {stderr}")
                    self.processes.pop(route_path, None)
                    self.start_times.pop(route_path, None)
                    raise TTYDStartupError(stderr=stderr)
                    
                if self.is_process_running(route_path):
                    # Single consolidated log message after successful start
                    logger.info(f"Started ttyd: {route_path} (port:{port}, pid:{process.pid})")
                    return
                    
                time.sleep(check_interval)
                
            logger.error(f"ttyd for route {route_path} did not start within the timeout")
            self.processes.pop(route_path, None)
            self.start_times.pop(route_path, None)
            raise TTYDStartupError(f"Timeout starting ttyd for route {route_path}")

        except subprocess.SubprocessError as e:
            logger.error(f"Failed to start ttyd for route {route_path}: {e}")
            raise TTYDStartupError(str(e))

    def stop(self) -> None:
        """
        Stop all running ttyd processes.
        """
        process_count = len(self.processes)
        if process_count == 0:
            logger.debug("No ttyd processes to stop")
            return
            
        logger.info(f"Stopping {process_count} ttyd processes")
        
        for route_path in list(self.processes.keys()):
            self.stop_process(route_path, log_individual=False)
            
        logger.info("All ttyd processes stopped")

    def stop_process(self, route_path: str, log_individual: bool = True) -> None:
        """
        Stop a single ttyd process for the given route.
        
        Args:
            route_path: The route path of the process to stop
            log_individual: Whether to log individual process stop (False when called from stop())
        """
        process = self.processes.get(route_path)
        if not process:
            return
            
        if log_individual:
            logger.info(f"Stopping ttyd for route {route_path}")
            
        try:
            if os.name == 'nt':
                process.terminate()
            else:
                try:
                    pgid = os.getpgid(process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    process.kill()
                else:
                    try:
                        pgid = os.getpgid(process.pid)
                        os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
        except Exception as e:
            logger.warning(f"Error cleaning up process for route {route_path}: {e}")
        
        self.processes.pop(route_path, None)
        self.start_times.pop(route_path, None)
        
        if log_individual:
            logger.info(f"Stopped ttyd for route {route_path}")

    def is_process_running(self, route_path: str) -> bool:
        """
        Check if the ttyd process for a given route is running.
        """
        process = self.processes.get(route_path)
        return bool(process and process.poll() is None)

    def get_process_uptime(self, route_path: str) -> Optional[float]:
        """
        Return the uptime in seconds for the specified route's process.
        """
        if self.is_process_running(route_path) and route_path in self.start_times:
            return (datetime.now() - self.start_times[route_path]).total_seconds()
        return None

    def check_health(self) -> Dict[str, Any]:
        """
        Gather health data for all processes, including status and uptime.
        """
        processes_health = []
        for cfg in self.config.script_configs:
            route_path = cfg.route_path
            running = self.is_process_running(route_path)
            processes_health.append({
                "route_path": route_path,
                "script": str(cfg.client_script),
                "status": "running" if running else "stopped",
                "uptime": self.get_process_uptime(route_path),
                "port": cfg.port,
                "pid": self.processes.get(route_path).pid if running else None,
                "title": cfg.title or self.config.title
            })
            
        # Log a compact summary of process health
        running_count = sum(1 for p in processes_health if p["status"] == "running")
        logger.debug(f"Health check: {running_count}/{len(processes_health)} processes running")
        
        entry_mode = getattr(self.config, '_mode', 'script')
        
        return {
            "processes": processes_health,
            "ttyd_path": str(self._ttyd_path) if self._ttyd_path else None,
            "is_multi_script": self.config.is_multi_script,
            "process_count": len(self.processes),
            "mounting": "root" if self.config.is_root_mounted else "non-root",
            "entry_mode": entry_mode,  # Add entry mode to health check
            **self.config.get_health_check_info()
        }

    def restart_process(self, route_path: str) -> None:
        """
        Restart the ttyd process for a given route.
        """
        logger.info(f"Restarting ttyd for route {route_path}")
        script_config = None
        for cfg in self.config.script_configs:
            if cfg.route_path == route_path:
                script_config = cfg
                break
        if not script_config:
            raise TTYDStartupError(f"No script configuration found for route {route_path}")
        
        self.stop_process(route_path)
        self.start_process(script_config)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        """
        Manage ttyd lifecycle within a FastAPI application lifespan.
        """
        try:
            self.start()
            yield
        finally:
            self.stop()
