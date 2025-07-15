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
from .wrappers import write_query_params_file

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

        self.terminal_configs = [
            cfg for cfg in config.route_configs if isinstance(cfg, ScriptConfig)
        ]
        self._log_proxy_configuration()

    def _log_proxy_configuration(self) -> None:
        """Log proxy configuration details."""
        entry_mode = getattr(self.config, "_mode", "script")
        server_mode = "apps-server" if self.config.is_multi_script else "solo-server"
        logger.debug(
            f"Proxy configured for {len(self.targets)} terminal routes "
            f"({entry_mode} API, {server_mode} mode)"
        )

    def _initialize_targets(self) -> None:
        """Build base URLs for each terminal route's ttyd process."""
        for route_config in self.config.route_configs:
            if isinstance(route_config, ScriptConfig) and route_config.port:
                host = f"{self.config.ttyd_options.interface}:{route_config.port}"
                http_url = f"http://{host}"
                self.targets[route_config.route_path] = {
                    "host": host,
                    "port": route_config.port,
                    "http_url": http_url,
                }

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
        """Retrieve the script config and target info for a given request path."""
        route_config = self.config.get_route_config_for_path(request_path)

        if not isinstance(route_config, ScriptConfig):
            raise RouteNotFoundError(f"No terminal route for path: {request_path}")

        target_info = self.targets.get(route_config.route_path)
        if not target_info:
            raise RouteNotFoundError(
                f"No target info for route: {route_config.route_path}"
            )

        return route_config, target_info

    def _strip_path_prefix(self, path: str, script_config: ScriptConfig) -> str:
        """Remove the configured prefix from the request path so ttyd sees the correct path."""
        route_path = script_config.route_path

        if route_path == "/":
            if self.config.is_root_mounted and path.startswith("/terminal/"):
                return path.replace("/terminal", "", 1)
            elif not self.config.is_root_mounted and path.startswith(
                self.config.terminal_path
            ):
                return path.replace(self.config.terminal_path, "", 1) or "/"
        else:
            terminal_path = self.config.get_terminal_path_for_route(route_path)
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

    # Pre-define header filter sets for performance
    _EXCLUDED_REQUEST_HEADERS = frozenset(["host"])
    _EXCLUDED_RESPONSE_HEADERS = frozenset(["content-encoding", "content-length", "transfer-encoding"])

    async def proxy_http(self, request: Request) -> Response:
        """Forward HTTP requests to the correct ttyd, adjusting paths and headers as needed."""
        path = request.url.path
        if path.endswith(".map"):
            return await self._handle_sourcemap(path)

        try:
            script_config, target_info = self._get_target_info(path)
            target_path = self._strip_path_prefix(path, script_config)
            # Optimize header filtering
            headers = {k: v for k, v in request.headers.items() if k.lower() not in self._EXCLUDED_REQUEST_HEADERS}

            response = await self.http_client.request(
                method=request.method, url=urljoin(target_info["http_url"], target_path),
                headers=headers, content=await request.body()
            )
            # Optimize response header filtering
            filtered_headers = {
                k: v for k, v in response.headers.items() if k.lower() not in self._EXCLUDED_RESPONSE_HEADERS
            }
            return StreamingResponse(
                response.aiter_bytes(),
                status_code=response.status_code,
                headers=filtered_headers,
                media_type=response.headers.get("content-type"),
            )
        except RouteNotFoundError as e:
            logger.error(f"Route not found: {e}")
            raise ProxyError(str(e))
        except httpx.RequestError as e:
            logger.error(f"HTTP proxy error: {e}")
            raise ProxyError(f"Failed to proxy request: {e}")

    async def proxy_websocket(
        self, websocket: WebSocket, route_path: Optional[str] = None
    ) -> None:
        """Forward WebSocket connections to ttyd, including bidirectional data flow."""
        try:
            script_config, route_path = await self._resolve_websocket_route(
                websocket, route_path
            )
            target_info = self.targets.get(route_path)
            if not target_info:
                raise RouteNotFoundError(f"No target info for route: {route_path}")

            ws_url = f"ws://{target_info['host']}/ws"
            await websocket.accept(subprotocol="tty")

            await self._handle_dynamic_route_params(
                script_config, route_path, websocket
            )
            self._log_websocket_connection(script_config, route_path)

            async with websockets.connect(
                ws_url, subprotocols=["tty"], ping_interval=None, close_timeout=5
            ) as target_ws:

                await self._bidirectional_forward(websocket, target_ws, route_path)

        except RouteNotFoundError as e:
            logger.error(f"WebSocket route not found: {e}")
            raise ProxyError(str(e))
        except Exception as e:
            if not isinstance(e, websockets.exceptions.ConnectionClosed):
                logger.error(f"WebSocket proxy error: {e}")
                raise ProxyError(f"WebSocket proxy error: {e}")
        finally:
            await self._safe_close_websocket(websocket)

    async def _resolve_websocket_route(
        self, websocket: WebSocket, route_path: Optional[str]
    ) -> Tuple[ScriptConfig, str]:
        """Resolve the script config and route path for a WebSocket connection."""
        if route_path is None:
            ws_path = websocket.url.path
            route_config = self.config.get_route_config_for_path(ws_path)
            if not isinstance(route_config, ScriptConfig):
                raise RouteNotFoundError(
                    f"No terminal route for WebSocket path: {ws_path}"
                )
            return route_config, route_config.route_path

        script_config = next(
            (cfg for cfg in self.terminal_configs if cfg.route_path == route_path), None
        )
        if not script_config:
            raise RouteNotFoundError(f"No terminal route found for path: {route_path}")
        return script_config, route_path

    async def _handle_dynamic_route_params(
        self, script_config: ScriptConfig, route_path: str, websocket: WebSocket
    ) -> None:
        """Handle query parameters for dynamic routes."""
        if script_config.dynamic:
            query_params = dict(websocket.query_params)
            try:
                write_query_params_file(route_path, query_params, self.config)
                log_msg = f"Wrote {'empty ' if not query_params else ''}query params for dynamic route {route_path}"
                if query_params:
                    log_msg += f": {query_params}"
                logger.debug(log_msg)
            except Exception as e:
                logger.error(
                    f"Failed to write query params for route {route_path}: {e}"
                )

    def _log_websocket_connection(
        self, script_config: ScriptConfig, route_path: str
    ) -> None:
        """Log WebSocket connection with colored title."""
        title = script_config.title or self.config.title
        colored_title = route_color_manager.colorize_title(title, route_path)
        logger.info(f"WebSocket connected: '{colored_title}' at {route_path}")

    async def _bidirectional_forward(
        self, websocket: WebSocket, target_ws: Any, route_path: str
    ) -> None:
        """Handle bidirectional WebSocket data forwarding."""

        async def forward(source: Any, dest: Any, is_client: bool = True) -> None:
            """Forward data between WebSocket connections."""
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
                            logger.error(f"WebSocket error for {route_path}: {e}")
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

    async def _safe_close_websocket(self, websocket: WebSocket) -> None:
        """Safely close a WebSocket connection."""
        try:
            await websocket.close()
        except Exception:
            pass

    def get_routes_info(self) -> Dict[str, Any]:
        """Return data for each proxy route, including endpoints and script info."""
        routes_info = [
            self._build_route_info(route_config)
            for route_config in self.config.route_configs
        ]

        return {
            "routes": routes_info,
            "mount_path": self.config.mount_path,
            "is_root_mounted": self.config.is_root_mounted,
            "is_multi_script": self.config.is_multi_script,
            "has_index_pages": self.config.has_index_pages,
            "entry_mode": getattr(self.config, "_mode", "script"),
        }

    def _build_route_info(self, route_config) -> Dict[str, Any]:
        """Build route information for a single route config."""
        route_path = route_config.route_path

        if isinstance(route_config, ScriptConfig):
            target_info = self.targets.get(route_path, {})
            return {
                "type": "terminal",
                "route_path": route_path,
                "script": str(route_config.effective_script_path),
                "terminal_path": self.config.get_terminal_path_for_route(route_path),
                "port": target_info.get("port"),
                "title": route_config.title or self.config.title,
            }
        elif isinstance(route_config, IndexPageConfig):
            return {
                "type": "index",
                "route_path": route_path,
                "title": route_config.title
                or getattr(route_config.index_page, "page_title", "Index"),
                "menu_items": len(route_config.index_page.get_all_menu_items()),
            }
