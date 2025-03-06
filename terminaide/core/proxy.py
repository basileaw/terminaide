# terminaide/core/proxy.py

"""
Proxy management for ttyd HTTP and WebSocket connections.

This module handles the proxying of both HTTP and WebSocket connections to the ttyd
processes, with special handling for path management to support both root and non-root
mounting configurations. It now supports multiple ttyd processes for different routes.
"""

import json
import logging
import asyncio
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urljoin

import httpx
import websockets
import websockets.exceptions
from fastapi import Request, WebSocket, HTTPException
from fastapi.responses import Response, StreamingResponse

from ..exceptions import ProxyError, RouteNotFoundError
from .settings import TTYDConfig, ScriptConfig

logger = logging.getLogger("terminaide")

class ProxyManager:
    """
    Manages HTTP and WebSocket proxying for ttyd while maintaining same-origin security.
    
    This class handles the complexities of proxying requests to ttyd processes,
    including path rewriting and WebSocket connection management. It supports both
    root ("/") and non-root ("/path") mounting configurations, as well as
    multiple script configurations for different routes.
    """
    
    def __init__(self, config: TTYDConfig):
        """
        Initialize the proxy manager.

        Args:
            config: TTYDConfig instance with proxy configuration
        """
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        
        # Track the targets for each script configuration
        self.targets: Dict[str, Dict[str, str]] = {}
        
        # Initialize target info for each script config
        self._initialize_targets()
        
        logger.info(
            f"Proxy configured for {len(self.targets)} ttyd targets "
            f"({'multi-script' if self.config.is_multi_script else 'single-script'} mode)"
        )

    def _initialize_targets(self) -> None:
        """Initialize target info for each script configuration."""
        for script_config in self.config.script_configs:
            route_path = script_config.route_path
            port = script_config.port
            
            if port is None:
                logger.error(f"Script config for route {route_path} has no port assigned")
                continue
                
            # Build base URLs for this ttyd process
            host = f"{self.config.ttyd_options.interface}:{port}"
            target_url = f"http://{host}"
            ws_url = f"ws://{host}/ws"
            
            # Store target info
            self.targets[route_path] = {
                "target_url": target_url,
                "ws_url": ws_url,
                "port": port
            }
            
            # Get terminal path for this route
            terminal_path = self.config.get_terminal_path_for_route(route_path)
            
            logger.info(
                f"Proxy route '{route_path}' configured for ttyd at {target_url} "
                f"(terminal path: {terminal_path})"
            )

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Lazy initialization of HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True
            )
        return self._client

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_target_info(self, request_path: str) -> Tuple[ScriptConfig, Dict[str, str]]:
        """
        Get target information for a given request path.
        
        This method finds the correct script configuration and target info
        for a specific request path.
        
        Args:
            request_path: Path from incoming request
            
        Returns:
            Tuple of (ScriptConfig, target_info_dict)
            
        Raises:
            RouteNotFoundError: If no matching route is found
        """
        # Get the script config for this path
        script_config = self.config.get_script_config_for_path(request_path)
        
        if not script_config:
            raise RouteNotFoundError(f"No script configuration found for path: {request_path}")
            
        # Get target info for this route
        route_path = script_config.route_path
        target_info = self.targets.get(route_path)
        
        if not target_info:
            raise RouteNotFoundError(f"No target information found for route: {route_path}")
            
        return script_config, target_info

    def _strip_path_prefix(self, path: str, script_config: ScriptConfig) -> str:
        """
        Strip the mount path prefix from the request path.
        
        This method handles both root and non-root mounting scenarios to ensure
        requests are properly forwarded to ttyd.
        
        Args:
            path: Original request path
            script_config: Script configuration for this request
            
        Returns:
            Path with prefix stripped for ttyd
        """
        route_path = script_config.route_path
        terminal_path = self.config.get_terminal_path_for_route(route_path)
        
        # For root script with root mounting
        if route_path == "/" and self.config.is_root_mounted:
            if path.startswith("/terminal/"):
                return path.replace("/terminal", "", 1)
            return "/"
            
        # For root script with non-root mounting
        if route_path == "/" and not self.config.is_root_mounted:
            prefix = self.config.terminal_path
            if path.startswith(prefix):
                return path.replace(prefix, "", 1) or "/"
            return "/"
            
        # For non-root scripts
        if path.startswith(f"{terminal_path}/"):
            return path.replace(terminal_path, "", 1) or "/"
        
        # Fallback
        return "/"

    async def _handle_sourcemap(self, path: str) -> Response:
        """Handle sourcemap requests with minimal response."""
        return Response(
            content=json.dumps({
                "version": 3,
                "file": path.split('/')[-1].replace('.map', ''),
                "sourceRoot": "",
                "sources": ["source.js"],
                "sourcesContent": ["// Source code unavailable"],
                "names": [],
                "mappings": ";;;;;;;",
            }),
            media_type='application/json',
            headers={'Access-Control-Allow-Origin': '*'}
        )

    async def proxy_http(self, request: Request) -> Response:
        """
        Proxy HTTP requests to the appropriate ttyd process.
        
        This method handles path rewriting and forwards the request to the correct ttyd
        process based on the request path.

        Args:
            request: Incoming FastAPI request

        Returns:
            Proxied response from ttyd

        Raises:
            ProxyError: If proxying fails
            RouteNotFoundError: If no matching route is found
        """
        path = request.url.path
        
        # Handle sourcemap requests
        if path.endswith('.map'):
            return await self._handle_sourcemap(path)
        
        try:
            # Get target info for this path
            script_config, target_info = self._get_target_info(path)
            
            # Strip the appropriate prefix based on mounting configuration
            target_path = self._strip_path_prefix(path, script_config)
            
            # Forward the request to ttyd
            headers = dict(request.headers)
            headers.pop("host", None)  # Remove host header
            
            response = await self.http_client.request(
                method=request.method,
                url=urljoin(target_info["target_url"], target_path),
                headers=headers,
                content=await request.body()
            )
            
            # Clean response headers that might cause issues
            response_headers = {
                k: v for k, v in response.headers.items()
                if k.lower() not in {
                    'content-encoding',
                    'content-length',
                    'transfer-encoding'
                }
            }
            
            return StreamingResponse(
                response.aiter_bytes(),
                status_code=response.status_code,
                headers=response_headers,
                media_type=response.headers.get('content-type')
            )

        except RouteNotFoundError as e:
            logger.error(f"Route not found: {e}")
            raise ProxyError(f"Failed to find route: {e}")
        except httpx.RequestError as e:
            logger.error(f"HTTP proxy error: {e}")
            raise ProxyError(f"Failed to proxy request: {e}")

    async def proxy_websocket(self, websocket: WebSocket, route_path: Optional[str] = None) -> None:
        """
        Proxy WebSocket connections to the appropriate ttyd process.
        
        This method handles the WebSocket connection to the correct ttyd process,
        including proper error handling and cleanup.

        Args:
            websocket: Incoming WebSocket connection
            route_path: Optional route path override (defaults to extracting from WebSocket path)

        Raises:
            ProxyError: If WebSocket proxying fails
            RouteNotFoundError: If no matching route is found
        """
        try:
            # If route_path not provided, extract from WebSocket URL path
            if route_path is None:
                ws_path = websocket.url.path
                
                # Try to get script config from the WebSocket path
                script_config = self.config.get_script_config_for_path(ws_path)
                
                if not script_config:
                    raise RouteNotFoundError(f"No script configuration found for WebSocket path: {ws_path}")
                    
                route_path = script_config.route_path
            
            # Get target info for this route
            target_info = self.targets.get(route_path)
            
            if not target_info:
                raise RouteNotFoundError(f"No target information found for route: {route_path}")
                
            ws_url = target_info["ws_url"]
            
            # Accept the incoming connection with ttyd subprotocol
            await websocket.accept(subprotocol='tty')
            
            logger.info(f"Opening WebSocket connection to {ws_url} for route {route_path}")
            
            async with websockets.connect(
                ws_url,
                subprotocols=['tty'],
                ping_interval=None,
                close_timeout=5
            ) as target_ws:
                logger.info(f"WebSocket connection established for route {route_path}")
                
                # Set up bidirectional forwarding
                async def forward(source: Any, dest: Any, is_client: bool = True) -> None:
                    """Forward data between WebSocket connections."""
                    try:
                        while True:
                            try:
                                # Handle different WebSocket implementations
                                if is_client:
                                    data = await source.receive_bytes()
                                    await dest.send(data)
                                else:
                                    data = await source.recv()
                                    if isinstance(data, bytes):
                                        await dest.send_bytes(data)
                                    else:
                                        await dest.send_text(data)
                            except websockets.exceptions.ConnectionClosed:
                                logger.info(
                                    f"{'Client' if is_client else 'Target'} "
                                    f"connection closed normally for route {route_path}"
                                )
                                break
                            except Exception as e:
                                if not isinstance(e, asyncio.CancelledError):
                                    logger.error(
                                        f"{'Client' if is_client else 'Target'} "
                                        f"connection error for route {route_path}: {e}"
                                    )
                                break

                    except asyncio.CancelledError:
                        logger.info(
                            f"{'Client' if is_client else 'Target'} "
                            f"forwarding cancelled for route {route_path}"
                        )
                        raise
                    except Exception as e:
                        if not isinstance(e, websockets.exceptions.ConnectionClosed):
                            logger.error(f"WebSocket forward error for route {route_path}: {e}")

                # Create forwarding tasks
                tasks = [
                    asyncio.create_task(forward(websocket, target_ws)),
                    asyncio.create_task(forward(target_ws, websocket, False))
                ]
                
                try:
                    # Wait for either direction to complete
                    await asyncio.wait(
                        tasks,
                        return_when=asyncio.FIRST_COMPLETED
                    )
                finally:
                    # Clean up tasks
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass

        except RouteNotFoundError as e:
            logger.error(f"Route not found for WebSocket: {e}")
            raise ProxyError(f"Failed to find route for WebSocket: {e}")
        except Exception as e:
            logger.error(f"WebSocket proxy error: {e}")
            if not isinstance(e, websockets.exceptions.ConnectionClosed):
                raise ProxyError(f"WebSocket proxy error: {e}")
        
        finally:
            # Ensure WebSocket is closed
            try:
                await websocket.close()
            except Exception:
                pass  # Connection already closed

    def get_routes_info(self) -> Dict[str, Any]:
        """Get information about proxy routes for monitoring."""
        routes_info = []
        
        for script_config in self.config.script_configs:
            route_path = script_config.route_path
            target_info = self.targets.get(route_path, {})
            
            route_info = {
                "route_path": route_path,
                "script": str(script_config.client_script),
                "terminal_path": self.config.get_terminal_path_for_route(route_path),
                "http_endpoint": target_info.get("target_url"),
                "ws_endpoint": target_info.get("ws_url"),
                "port": target_info.get("port"),
                "title": script_config.title or self.config.title
            }
            
            routes_info.append(route_info)
            
        return {
            "routes": routes_info,
            "mount_path": self.config.mount_path,
            "is_root_mounted": self.config.is_root_mounted,
            "is_multi_script": self.config.is_multi_script
        }