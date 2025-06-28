# proxy.py

"""Manages HTTP and WebSocket proxying for ttyd processes, including path rewriting and multiple-route support."""

import json
import logging
import asyncio
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urljoin

import httpx
import websockets
import websockets.exceptions
from fastapi import Request, WebSocket
from fastapi.responses import Response, StreamingResponse

from .exceptions import ProxyError, RouteNotFoundError
from .models import TTYDConfig, ScriptConfig, IndexPageConfig
from .logger import route_color_manager
from .dynamic_wrapper import write_query_params_file

# Get logger without configuring it (configuration happens in serve methods)
logger = logging.getLogger("terminaide")


class ProxyManager:
    """Handles HTTP and WebSocket traffic to ttyd, including path prefix adjustments and multi-route configurations."""

    def __init__(self, config: TTYDConfig):
        """
        Initialize the proxy manager with the given TTYDConfig.
        """
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self.targets: Dict[str, Dict[str, str]] = {}
        self._initialize_targets()

        # Filter to only terminal routes
        self.terminal_configs = [
            cfg for cfg in config.route_configs if isinstance(cfg, ScriptConfig)
        ]

        # Debug-level logging for proxy configuration
        entry_mode = getattr(self.config, "_mode", "script")
        logger.debug(
            f"Proxy configured for {len(self.targets)} terminal routes "
            f"({entry_mode} API, {'apps-server' if self.config.is_multi_script else 'solo-server'} mode)"
        )

    def _get_request_protocol(self, request: Optional[Request] = None) -> str:
        """
        Get the protocol (http/https) for the current request.

        This looks at the request.url.scheme, which will be correctly set to 'https'
        by the proxy header middleware if the request came via HTTPS.
        """
        if request and request.url.scheme == "https":
            return "https"
        return "http"

    def _get_ws_protocol(self, request_protocol: str) -> str:
        """
        Get the WebSocket protocol (ws/wss) based on HTTP protocol.
        """
        return "wss" if request_protocol == "https" else "ws"

    def _initialize_targets(self) -> None:
        """
        Build base URLs for each terminal route's ttyd process.
        """
        # Only process ScriptConfig routes
        for route_config in self.config.route_configs:
            if isinstance(route_config, ScriptConfig):
                route_path = route_config.route_path
                port = route_config.port
                if port is None:
                    logger.error(f"No port assigned to terminal route {route_path}")
                    continue
                host = f"{self.config.ttyd_options.interface}:{port}"
                self.targets[route_path] = {"host": host, "port": port}

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Create and return a reusable AsyncClient."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0), follow_redirects=True
            )
        return self._client

    async def cleanup(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_target_info(
        self, request_path: str
    ) -> Tuple[ScriptConfig, Dict[str, str]]:
        """
        Retrieve the script config and target info for a given request path.
        """
        # Use the existing method that returns the route config
        route_config = self.config.get_route_config_for_path(request_path)

        # Ensure it's a ScriptConfig (terminal route)
        if not route_config or not isinstance(route_config, ScriptConfig):
            raise RouteNotFoundError(f"No terminal route for path: {request_path}")

        route_path = route_config.route_path
        target_info = self.targets.get(route_path)
        if not target_info:
            raise RouteNotFoundError(f"No target info for route: {route_path}")

        return route_config, target_info

    def _strip_path_prefix(self, path: str, script_config: ScriptConfig) -> str:
        """
        Remove the configured prefix from the request path so ttyd sees the correct path.
        """
        route_path = script_config.route_path
        terminal_path = self.config.get_terminal_path_for_route(route_path)

        # Root script with root mounting
        if route_path == "/" and self.config.is_root_mounted:
            if path.startswith("/terminal/"):
                return path.replace("/terminal", "", 1)
            return "/"
        # Root script with non-root mounting
        if route_path == "/" and not self.config.is_root_mounted:
            prefix = self.config.terminal_path
            if path.startswith(prefix):
                return path.replace(prefix, "", 1) or "/"
            return "/"
        # Non-root scripts
        if path.startswith(f"{terminal_path}/"):
            return path.replace(terminal_path, "", 1) or "/"
        return "/"

    async def _handle_sourcemap(self, path: str) -> Response:
        """Return a minimal sourcemap response."""
        return Response(
            content=json.dumps(
                {
                    "version": 3,
                    "file": path.split("/")[-1].replace(".map", ""),
                    "sourceRoot": "",
                    "sources": ["source.js"],
                    "sourcesContent": ["// Source code unavailable"],
                    "names": [],
                    "mappings": ";;;;;;;",
                }
            ),
            media_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    async def proxy_http(self, request: Request) -> Response:
        """
        Forward HTTP requests to the correct ttyd, adjusting paths and headers as needed.
        """
        path = request.url.path
        if path.endswith(".map"):
            return await self._handle_sourcemap(path)

        try:
            script_config, target_info = self._get_target_info(path)
            target_path = self._strip_path_prefix(path, script_config)
            headers = dict(request.headers)
            headers.pop("host", None)

            # Always use http for internal proxying to ttyd
            host = target_info["host"]
            target_url = f"http://{host}"

            response = await self.http_client.request(
                method=request.method,
                url=urljoin(target_url, target_path),
                headers=headers,
                content=await request.body(),
            )
            # Filter certain response headers
            filtered_headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower()
                not in {"content-encoding", "content-length", "transfer-encoding"}
            }
            return StreamingResponse(
                response.aiter_bytes(),
                status_code=response.status_code,
                headers=filtered_headers,
                media_type=response.headers.get("content-type"),
            )
        except RouteNotFoundError as e:
            logger.error(f"Route not found: {e}")
            raise ProxyError(f"Route not found: {e}")
        except httpx.RequestError as e:
            logger.error(f"HTTP proxy error: {e}")
            raise ProxyError(f"Failed to proxy request: {e}")

    async def proxy_websocket(
        self, websocket: WebSocket, route_path: Optional[str] = None
    ) -> None:
        """
        Forward WebSocket connections to ttyd, including bidirectional data flow.
        """
        try:
            if route_path is None:
                ws_path = websocket.url.path
                route_config = self.config.get_route_config_for_path(ws_path)
                if not route_config or not isinstance(route_config, ScriptConfig):
                    raise RouteNotFoundError(
                        f"No terminal route for WebSocket path: {ws_path}"
                    )
                route_path = route_config.route_path
                script_config = route_config
            else:
                # Find the script config for the given route path
                script_config = None
                for cfg in self.terminal_configs:
                    if cfg.route_path == route_path:
                        script_config = cfg
                        break

                if not script_config:
                    raise RouteNotFoundError(
                        f"No terminal route found for path: {route_path}"
                    )

            target_info = self.targets.get(route_path)
            if not target_info:
                raise RouteNotFoundError(f"No target info for route: {route_path}")

            host = target_info["host"]
            ws_url = f"ws://{host}/ws"

            await websocket.accept(subprotocol="tty")
            
            # Handle dynamic routes - extract query params and write to temp file
            if script_config and script_config.dynamic:
                query_params = dict(websocket.query_params)
                try:
                    param_file = write_query_params_file(route_path, query_params)
                    if query_params:
                        logger.debug(f"Wrote query params for dynamic route {route_path}: {query_params}")
                    else:
                        logger.debug(f"Wrote empty query params for dynamic route {route_path}")
                except Exception as e:
                    logger.error(f"Failed to write query params for route {route_path}: {e}")

            # Simplified WebSocket connection logging
            if script_config:
                title = script_config.title or self.config.title
                colored_title = route_color_manager.colorize_title(title, route_path)
                logger.info(f"WebSocket connected: '{colored_title}' at {route_path}")

            async with websockets.connect(
                ws_url, subprotocols=["tty"], ping_interval=None, close_timeout=5
            ) as target_ws:

                async def forward(
                    source: Any, dest: Any, is_client: bool = True
                ) -> None:
                    """Bidirectional WebSocket data forwarding."""
                    try:
                        while True:
                            try:
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
                                    f"{'Client' if is_client else 'Target'} connection closed for {route_path}"
                                )
                                break
                            except Exception as e:
                                if not isinstance(e, asyncio.CancelledError):
                                    logger.error(
                                        f"WebSocket error for {route_path}: {e}"
                                    )
                                break
                    except asyncio.CancelledError:
                        logger.info(
                            f"{'Client' if is_client else 'Target'} forwarding cancelled for {route_path}"
                        )
                        raise

                tasks = [
                    asyncio.create_task(forward(websocket, target_ws)),
                    asyncio.create_task(forward(target_ws, websocket, False)),
                ]
                try:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass

        except RouteNotFoundError as e:
            logger.error(f"WebSocket route not found: {e}")
            raise ProxyError(f"No WebSocket route: {e}")
        except Exception as e:
            logger.error(f"WebSocket proxy error: {e}")
            if not isinstance(e, websockets.exceptions.ConnectionClosed):
                raise ProxyError(f"WebSocket proxy error: {e}")
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    def get_routes_info(self) -> Dict[str, Any]:
        """
        Return data for each proxy route, including endpoints and script info.
        """
        routes_info = []

        # Process all route configs, not just terminal ones
        for route_config in self.config.route_configs:
            route_path = route_config.route_path

            if isinstance(route_config, ScriptConfig):
                target_info = self.targets.get(route_path, {})
                routes_info.append(
                    {
                        "type": "terminal",
                        "route_path": route_path,
                        "script": str(route_config.effective_script_path),
                        "terminal_path": self.config.get_terminal_path_for_route(
                            route_path
                        ),
                        "port": target_info.get("port"),
                        "title": route_config.title or self.config.title,
                    }
                )
            elif isinstance(route_config, IndexPageConfig):
                routes_info.append(
                    {
                        "type": "index",
                        "route_path": route_path,
                        "title": route_config.title
                        or getattr(route_config.index_page, "page_title", "Index"),
                        "menu_items": len(route_config.index_page.get_all_menu_items()),
                    }
                )

        entry_mode = getattr(self.config, "_mode", "script")

        return {
            "routes": routes_info,
            "mount_path": self.config.mount_path,
            "is_root_mounted": self.config.is_root_mounted,
            "is_multi_script": self.config.is_multi_script,
            "has_index_pages": self.config.has_index_pages,
            "entry_mode": entry_mode,
        }
