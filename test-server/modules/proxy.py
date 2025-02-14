# backend/modules/proxy.py
import logging
import asyncio
import json
import httpx
import websockets
from fastapi import FastAPI, Request, WebSocket, HTTPException
from fastapi.responses import Response, StreamingResponse
from typing import Optional
from urllib.parse import urljoin

logger = logging.getLogger("uvicorn")

class ProxyManager:
    """Manages HTTP and WebSocket proxying while maintaining same-origin behavior."""
    def __init__(self, target_host: str, target_port: int):
        self.target_url = f"http://{target_host}:{target_port}"
        self.ws_url = f"ws://{target_host}:{target_port}/ws"
        self._client = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True)
        return self._client

    async def cleanup(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _handle_source_map(self, path: str) -> Response:
        return Response(
            content=json.dumps({
                "version": 3,
                "file": path.split('/')[-1].replace('.map', ''),
                "sourceRoot": "",
                "sources": ["source.js"],
                "sourcesContent": ["// Source code unavailable"],
                "names": [],
                "mappings": ";;;;;;;",
                "x_google_ignoreList": [0]
            }),
            media_type='application/json; charset=utf-8',
            headers={'Access-Control-Allow-Origin': '*', 'SourceMap': 'null'}
        )

    async def proxy_http(self, request: Request, strip_prefix: str = "") -> Response:
        path = request.url.path
        if strip_prefix and path.startswith(strip_prefix):
            path = path.replace(strip_prefix, "", 1) or "/"
        if path.endswith('.map'):
            return await self._handle_source_map(path)

        try:
            headers = dict(request.headers)
            headers.pop("host", None)
            response = await self.http_client.request(
                method=request.method,
                url=urljoin(self.target_url, path),
                headers=headers,
                content=await request.body()
            )
            
            response_headers = {k: v for k, v in response.headers.items() 
                              if k not in ['content-encoding', 'content-length', 'transfer-encoding']}
            
            return StreamingResponse(
                response.aiter_bytes(),
                status_code=response.status_code,
                headers=response_headers,
                media_type=response.headers.get('content-type')
            )
        except httpx.RequestError as e:
            logger.error(f"Proxy error: {e}")
            raise HTTPException(status_code=502, detail="Failed to proxy request")

    async def proxy_websocket(self, websocket: WebSocket, subprotocols: Optional[list] = None) -> None:
        try:
            await websocket.accept(subprotocol=subprotocols[0] if subprotocols else None)
            
            async with websockets.connect(
                self.ws_url,
                subprotocols=subprotocols or [],
                ping_interval=None,
                close_timeout=5
            ) as target_ws:
                async def forward(source, dest, is_client=True):
                    try:
                        while True:
                            data = await source.receive_bytes() if is_client else await source.recv()
                            if is_client:
                                await dest.send(data)
                            else:
                                await dest.send_bytes(data) if isinstance(data, bytes) else dest.send_text(data)
                    except Exception as e:
                        if not isinstance(e, asyncio.CancelledError):
                            logger.debug(f"{'Client' if is_client else 'Target'} disconnected: {e}")

                tasks = [
                    asyncio.create_task(forward(websocket, target_ws)),
                    asyncio.create_task(forward(target_ws, websocket, False))
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
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            try:
                if not websocket.client_state.DISCONNECTED:
                    await websocket.close()
            except Exception:
                pass  # Connection already closed

def setup_proxy_routes(app: FastAPI, proxy: ProxyManager, prefix: str = "/ttyd", ws_path: str = "/ws"):
    @app.websocket(f"{prefix}{ws_path}")
    async def proxy_ws(websocket: WebSocket):
        await proxy.proxy_websocket(websocket, ['tty'])
    
    @app.api_route(f"{prefix}{{path:path}}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE"])
    async def proxy_http(request: Request, path: str):
        return await proxy.proxy_http(request, strip_prefix=prefix)