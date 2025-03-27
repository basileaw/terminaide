# terminaide/core/manager.py

"""
Manages TTYd processes for single or multi-script setups, ensuring their
lifecycle, cleanup, and health monitoring.
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
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from ..exceptions import TTYDStartupError, TTYDProcessError, PortAllocationError
from ..installer import setup_ttyd
from .settings import TTYDConfig, ScriptConfig

logger = logging.getLogger("terminaide")


class TTYDManager:
    """
    Manages the lifecycle of ttyd processes, including startup, shutdown,
    health checks, resource cleanup, and port allocation.
    Supports single or multi-script configurations.
    """
    
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
            logger.info(f"Using ttyd binary at: {self._ttyd_path}")
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
        
        for cfg in configs_to_assign:
            while (next_port in assigned_ports
                   or self._is_port_in_use("127.0.0.1", next_port)):
                next_port += 1
                if next_port > 65000:
                    raise PortAllocationError("Port range exhausted")
            cfg.port = next_port
            assigned_ports.add(next_port)
            next_port += 1

        for cfg in self.config.script_configs:
            logger.info(f"Assigned port {cfg.port} to route {cfg.route_path}")

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

        if self.config.ttyd_options.writable:
            cmd.append('--writable')
        else:
            cmd.append('-R')
        
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
            
        logger.info(
            f"Starting {len(self.config.script_configs)} ttyd processes "
            f"({'multi-script' if self.config.is_multi_script else 'single-script'} mode)"
        )
        
        for script_config in self.config.script_configs:
            self.start_process(script_config)

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
        cmd_str = ' '.join(cmd)
        logger.info(f"Starting ttyd for route {route_path} with command: {cmd_str}")

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
                    logger.info(
                        f"ttyd started for route {route_path} with PID {process.pid} on port {port}"
                    )
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
        logger.info(f"Stopping all ttyd processes ({len(self.processes)} total)")
        for route_path in list(self.processes.keys()):
            self.stop_process(route_path)
        self.processes.clear()
        self.start_times.clear()
        logger.info("All ttyd processes stopped")

    def stop_process(self, route_path: str) -> None:
        """
        Stop a single ttyd process for the given route.
        """
        process = self.processes.get(route_path)
        if not process:
            return
            
        logger.info(f"Stopping ttyd for route {route_path}...")
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
        logger.info(f"ttyd for route {route_path} stopped")

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