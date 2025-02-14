# protottyde/core/proxy.py

"""
Proxy management for ttyd HTTP and WebSocket connections.

This module handles the proxying of both HTTP and WebSocket connections to the ttyd
process, with special handling for path management to support both root and non-root
mounting configurations.
"""

import json
import logging
import asyncio
from typing import Optional, Dict, Any
from urllib.parse import urljoin

import httpx
import websockets
import websockets.exceptions
from fastapi import Request, WebSocket, HTTPException
from fastapi.responses import Response, StreamingResponse

from ..exceptions import ProxyError
from .settings import TTYDConfig

logger = logging.getLogger("protottyde")

class ProxyManager:
    """
    Manages HTTP and WebSocket proxying for ttyd while maintaining same-origin security.
    
    This class handles the complexities of proxying requests to the ttyd process,
    including path rewriting and WebSocket connection management. It supports both
    root ("/") and non-root ("/path") mounting configurations.
    """
    
    def __init__(self, config: TTYDConfig):
        """
        Initialize the proxy manager.

        Args:
            config: TTYDConfig instance with proxy configuration
        """
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        
        # Build base URLs for the ttyd process
        host = f"{self.config.ttyd_options.interface}:{self.config.port}"
        self.target_url = f"http://{host}"
        self.ws_url = f"ws://{host}/ws"
        
        logger.info(
            f"Proxy configured for ttyd at {self.target_url} "
            f"(terminal path: {self.config.terminal_path})"
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

    def _strip_path_prefix(self, path: str) -> str:
        """
        Strip the mount path prefix from the request path.
        
        This method handles both root and non-root mounting scenarios to ensure
        requests are properly forwarded to ttyd.
        
        Args:
            path: Original request path
            
        Returns:
            Path with prefix stripped for ttyd
        """
        # For root mounting, we only need to strip the /terminal prefix
        if self.config.is_root_mounted:
            if path.startswith("/terminal/"):
                return path.replace("/terminal", "", 1)
            return "/"
            
        # For non-root mounting, strip both the mount path and /terminal
        prefix = self.config.terminal_path
        if path.startswith(prefix):
            return path.replace(prefix, "", 1) or "/"
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
        Proxy HTTP requests to ttyd.
        
        This method handles path rewriting and forwards the request to the ttyd
        process, supporting both root and non-root mounting configurations.

        Args:
            request: Incoming FastAPI request

        Returns:
            Proxied response from ttyd

        Raises:
            ProxyError: If proxying fails
        """
        path = request.url.path
        
        # Handle sourcemap requests
        if path.endswith('.map'):
            return await self._handle_sourcemap(path)
            
        # Strip the appropriate prefix based on mounting configuration
        target_path = self._strip_path_prefix(path)
        
        try:
            # Forward the request to ttyd
            headers = dict(request.headers)
            headers.pop("host", None)  # Remove host header
            
            response = await self.http_client.request(
                method=request.method,
                url=urljoin(self.target_url, target_path),
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

        except httpx.RequestError as e:
            logger.error(f"HTTP proxy error: {e}")
            raise ProxyError(f"Failed to proxy request: {e}")

    async def proxy_websocket(self, websocket: WebSocket) -> None:
        """
        Proxy WebSocket connections to ttyd.
        
        This method handles the WebSocket connection to the ttyd process,
        including proper error handling and cleanup.

        Args:
            websocket: Incoming WebSocket connection

        Raises:
            ProxyError: If WebSocket proxying fails
        """
        try:
            # Accept the incoming connection with ttyd subprotocol
            await websocket.accept(subprotocol='tty')
            
            logger.info(f"Opening WebSocket connection to {self.ws_url}")
            
            async with websockets.connect(
                self.ws_url,
                subprotocols=['tty'],
                ping_interval=None,
                close_timeout=5
            ) as target_ws:
                logger.info("WebSocket connection established")
                
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
                                    "connection closed normally"
                                )
                                break
                            except Exception as e:
                                if not isinstance(e, asyncio.CancelledError):
                                    logger.error(
                                        f"{'Client' if is_client else 'Target'} "
                                        f"connection error: {e}"
                                    )
                                break

                    except asyncio.CancelledError:
                        logger.info(
                            f"{'Client' if is_client else 'Target'} "
                            "forwarding cancelled"
                        )
                        raise
                    except Exception as e:
                        if not isinstance(e, websockets.exceptions.ConnectionClosed):
                            logger.error(f"WebSocket forward error: {e}")

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
        return {
            "http_endpoint": self.target_url,
            "ws_endpoint": self.ws_url,
            "mount_path": self.config.mount_path,
            "terminal_path": self.config.terminal_path,
            "is_root_mounted": self.config.is_root_mounted
        }