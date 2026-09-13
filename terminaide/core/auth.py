"""
Token authentication for terminal routes.

Terminaide serves interactive, writable shells. Unauthenticated terminals
must be impossible by construction, so terminal routes are protected by a
token whenever the server is reachable beyond loopback and no other
authentication is configured.

The model is deliberately Jupyter-like:

- Local-only servers (loopback bind) stay frictionless: no token.
- Exposed servers without explicit credentials get an auto-generated session
  token, printed to the server console as a ready-to-click URL.
- The token can also be set explicitly (``auth_token=...`` or the
  ``TERMINAIDE_TOKEN`` environment variable) for scripted deployments.

A validated token is stored in an HttpOnly cookie so that navigation between
index pages, terminal pages, and the terminal iframe's WebSocket/assets works
without the token appearing in every URL.
"""

import hmac
import logging
import os
import secrets
from typing import Optional, Set, Tuple
from urllib.parse import unquote

from .models import TTYDConfig, ScriptConfig

logger = logging.getLogger("terminaide")

COOKIE_NAME = "terminaide_token"
QUERY_PARAM = "token"
HEADER_NAME = "x-terminaide-token"

LOOPBACK_HOSTS = frozenset(["127.0.0.1", "localhost", "::1"])


def is_loopback_host(host: Optional[str]) -> bool:
    """True if the host binds only to the loopback interface.

    Wildcard binds (0.0.0.0, ::) and specific external addresses are NOT
    loopback: they are reachable from the network.
    """
    if not host:
        return False
    return host in LOOPBACK_HOSTS


def resolve_auth_token(config) -> Optional[str]:
    """Resolve the effective auth token for a configuration.

    Precedence:
    1. Explicit ``auth_token`` on the config (``""`` explicitly disables auth)
    2. ``TERMINAIDE_TOKEN`` environment variable (``""`` disables)
    3. Auto-generation when the server binds a non-loopback host and no ttyd
       credentials are configured

    Returns the token to enforce, or None when terminal routes stay open.

    As a side effect, an auto-generated token is exported to the environment
    so that any re-creation of the app in the same process (hot reload
    children) reuses the same token the operator was shown.
    """
    token: Optional[str] = config.auth_token

    if token is None:
        token = os.environ.get("TERMINAIDE_TOKEN")

    if token == "":
        logger.warning(
            "Terminal token authentication explicitly disabled "
            "(auth_token=''). Terminals are unauthenticated - make sure the "
            "server is not exposed or is protected by your own auth."
        )
        return None

    if token:
        return token

    # No explicit token: decide whether one is required
    ttyd_options = config.ttyd_options if hasattr(config, "ttyd_options") else {}
    credential_required = (
        ttyd_options.get("credential_required", False)
        if isinstance(ttyd_options, dict)
        else getattr(ttyd_options, "credential_required", False)
    )
    host = getattr(config, "host", "127.0.0.1")

    if credential_required:
        # ttyd's own basic-auth credentials protect the terminals
        return None

    if is_loopback_host(host):
        # Local-only server: stay frictionless
        return None

    token = secrets.token_urlsafe(24)
    # Export so reload children / repeated conversions reuse the same token
    os.environ["TERMINAIDE_TOKEN"] = token
    logger.warning(
        f"Terminaide is serving on a non-loopback interface ({host}) without "
        "credentials. A session token was auto-generated and is required for "
        f"terminal routes: append ?{QUERY_PARAM}=<token> to terminal URLs. "
        "Set TERMINAIDE_TOKEN or auth_token to choose your own, or "
        "auth_token='' to disable this protection."
    )
    return token


def extract_token(scope) -> Tuple[Optional[str], Optional[str]]:
    """Extract a candidate token from an ASGI scope.

    Returns (token, source) where source is "query", "header" or "cookie".
    The source matters: a fresh query-string token triggers cookie issuance.
    """
    # Query string: ?token=...
    query_string = scope.get("query_string", b"").decode("latin1")
    for part in query_string.split("&"):
        if part.startswith(f"{QUERY_PARAM}="):
            candidate = unquote(part[len(QUERY_PARAM) + 1 :])
            return (candidate, "query") if candidate else (None, None)

    # Headers: X-Terminaide-Token or the auth cookie
    for key, value in scope.get("headers", []):
        name = key.decode("latin1").lower()
        if name == HEADER_NAME:
            return value.decode("latin1") or None, "header"
        if name == "cookie":
            for cookie in value.decode("latin1").split(";"):
                cookie = cookie.strip()
                if cookie.startswith(f"{COOKIE_NAME}="):
                    return cookie[len(COOKIE_NAME) + 1 :] or None, "cookie"

    return None, None


class TokenAuthMiddleware:
    """Raw ASGI middleware enforcing token auth on terminal routes.

    Protects the terminal HTML pages and everything under their terminal
    paths (WebSocket + proxied ttyd traffic). Index pages and /health stay
    public so navigation and monitoring work without credentials.

    Installed only when a resolved token exists (see resolve_auth_token).
    """

    def __init__(self, app, ttyd_config: TTYDConfig):
        self.app = app
        self.token = ttyd_config.auth_token
        self.mount_path = ttyd_config.mount_path or "/"
        # (route_path, terminal_path) pairs to protect
        self.protected: Set[Tuple[str, str]] = set()
        for route_config in ttyd_config.route_configs:
            if isinstance(route_config, ScriptConfig):
                self.protected.add(
                    (route_config.route_path, ttyd_config.get_terminal_path_for_route(route_config.route_path))
                )

    def _is_protected_path(self, path: str) -> bool:
        for route_path, terminal_path in self.protected:
            if path == route_path:
                return True
            if path == terminal_path or path.startswith(terminal_path + "/"):
                return True
        return False

    def _check(self, scope) -> Tuple[bool, Optional[str]]:
        """Validate the request's token. Returns (authorized, source)."""
        provided, source = extract_token(scope)
        if not provided:
            return False, source
        return hmac.compare_digest(provided, self.token), source

    async def __call__(self, scope, receive, send):
        if self.token is None or scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not self._is_protected_path(path):
            await self.app(scope, receive, send)
            return

        authorized, source = self._check(scope)
        if not authorized:
            if scope["type"] == "websocket":
                # Reject before accepting the handshake
                await send({"type": "websocket.close", "code": 1008, "reason": "Unauthorized"})
            else:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            (b"content-type", b"text/plain; charset=utf-8"),
                            (b"cache-control", b"no-store"),
                        ],
                    }
                )
                message = (
                    b"401 Unauthorized: this terminal requires an auth token.\n"
                    b"Open the tokenized URL shown in the server console, or append "
                    b"?token=<your token> to this URL."
                )
                await send({"type": "http.response.body", "body": message})
            return

        if scope["type"] == "http" and source == "query":
            # Fresh query-string auth: issue the cookie so subsequent requests
            # (terminal iframe, WebSocket, menu navigation) authenticate
            # without the token in every URL
            send = self._cookie_injecting_send(send, self._cookie_value(scope))

        await self.app(scope, receive, send)

    def _cookie_value(self, scope) -> str:
        parts = [
            f"{COOKIE_NAME}={self.token}",
            f"Path={self.mount_path}",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if scope.get("scheme") == "https":
            parts.append("Secure")
        return "; ".join(parts)

    @staticmethod
    def _cookie_injecting_send(send, cookie: str):
        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"set-cookie", cookie.encode("latin1")))
                message = dict(message)
                message["headers"] = headers
            await send(message)

        return wrapped_send
