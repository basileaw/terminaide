"""
Security-focused tests for terminaide hardening.

Covers:
- ttyd loopback binding by default (network isolation of backends)
- Port-conflict handling (never SIGKILL unrelated processes)
- Download integrity verification
- Health endpoint information disclosure
- Proxy header hygiene
- Per-connection parameter files
- WebSocket rate limiting
"""

import socket
import subprocess
import time
from pathlib import Path

import pytest

from terminaide.core.models import TTYDConfig, ScriptConfig, TTYDOptions
from terminaide.core.exceptions import TTYDStartupError


def free_port() -> int:
    """Allocate a currently-free TCP port on loopback."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_port(port: int, timeout: float = 10.0) -> bool:
    """Wait until a TCP port accepts connections (ttyd needs a moment)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.1)
    return False


def make_test_script(tmp_path: Path) -> Path:
    script = tmp_path / "hello.py"
    script.write_text("print('hello from terminaide test')\n")
    return script


def make_manager(tmp_path: Path, interface: str = None, port: int = None):
    port = port or free_port()
    options = TTYDOptions(port=port)
    if interface is not None:
        options.interface = interface
    script = make_test_script(tmp_path)
    config = TTYDConfig(
        port=port,
        ttyd_options=options,
        route_configs=[ScriptConfig(route_path="/", script=script, port=port)],
    )
    from terminaide.core.terminal import TTYDManager

    return TTYDManager(config)


# =============================================================================
# Fix 1: ttyd loopback binding
# =============================================================================


class TestConnectHost:
    """TTYDOptions.connect_host resolves wildcard binds to loopback."""

    def test_loopback_default(self):
        assert TTYDOptions().interface == "127.0.0.1"

    def test_wildcard_resolves_to_loopback(self):
        assert TTYDOptions(interface="0.0.0.0").connect_host == "127.0.0.1"
        assert TTYDOptions(interface="::").connect_host == "127.0.0.1"
        assert TTYDOptions(interface="").connect_host == "127.0.0.1"

    def test_specific_host_preserved(self):
        assert TTYDOptions(interface="10.0.0.5").connect_host == "10.0.0.5"


class TestTTYDLoopbackBinding:
    """ttyd processes bind loopback by default; the proxy dials loopback."""

    def test_build_command_binds_loopback_by_default(self, tmp_path):
        manager = make_manager(tmp_path)
        cmd = manager._build_command(manager.terminal_configs[0])
        assert cmd[cmd.index("-i") + 1] == "127.0.0.1"

    def test_explicit_interface_still_respected(self, tmp_path):
        manager = make_manager(tmp_path, interface="0.0.0.0")
        cmd = manager._build_command(manager.terminal_configs[0])
        assert cmd[cmd.index("-i") + 1] == "0.0.0.0"

    def test_proxy_targets_dial_connect_host(self, tmp_path):
        # Wildcard bind: ttyd listens on 0.0.0.0 but proxy must dial loopback
        manager = make_manager(tmp_path, interface="0.0.0.0")
        from terminaide.core.proxy import ProxyManager

        proxy = ProxyManager(manager.config)
        target = proxy.targets["/"]
        assert target["host"].startswith("127.0.0.1:")

    def test_started_ttyd_listens_only_on_loopback(self, tmp_path):
        """Integration: an actually-started ttyd is not reachable on a
        non-loopback interface."""
        manager = make_manager(tmp_path)
        port = manager.terminal_configs[0].port
        manager.start()
        try:
            # Loopback should accept connections (ttyd needs a moment to bind)
            assert wait_for_port(port), "ttyd did not start listening on loopback"

            # The machine's non-loopback addresses should refuse it.
            hostname = socket.gethostname()
            ext_ips = []
            try:
                for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                    ip = info[4][0]
                    if not ip.startswith("127."):
                        ext_ips.append(ip)
            except Exception:
                pass

            for ip in ext_ips[:1]:  # one external address is enough
                with socket.socket() as s:
                    s.settimeout(2)
                    assert (
                        s.connect_ex((ip, port)) != 0
                    ), f"ttyd unexpectedly reachable on {ip}:{port}"
        finally:
            manager.stop()


# =============================================================================
# Fix 2: port-conflict handling
# =============================================================================


class TestPortConflictSafety:
    """A port occupied by an unrelated process must produce a clear error,
    never a silent SIGKILL."""

    def test_foreign_process_on_port_raises_clear_error(self, tmp_path):
        port = free_port()
        # Start an unrelated process listening on the configured port.
        # Use a real backlog so probes don't saturate it and confuse
        # port-in-use checks.
        listener = subprocess.Popen(
            [
                "python",
                "-c",
                "import socket,time;"
                "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
                f"s.bind(('127.0.0.1',{port}));s.listen(128);"
                "time.sleep(60)",
            ]
        )
        try:
            assert wait_for_port(port), "test listener did not start"

            manager = make_manager(tmp_path, port=port)
            with pytest.raises(TTYDStartupError, match="PID"):
                manager.start_process(manager.terminal_configs[0])

            # The foreign process must still be alive
            assert listener.poll() is None
        finally:
            listener.terminate()
            listener.wait(timeout=5)

    def test_own_leftover_ttyd_is_killed_and_port_reused(self, tmp_path):
        """A leftover ttyd process spawned from the terminaide-managed binary
        is still cleaned up automatically (zombie cleanup behavior)."""
        manager = make_manager(tmp_path)
        port = manager.terminal_configs[0].port

        # Simulate a leftover ttyd from a crashed run, using the same binary
        leftover = subprocess.Popen(
            [
                str(manager._ttyd_path),
                "-p",
                str(port),
                "-i",
                "127.0.0.1",
                "python",
                "-c",
                "import time; time.sleep(60)",
            ]
        )
        try:
            assert wait_for_port(port), "leftover ttyd did not start"

            # Starting the manager for that route must kill the leftover
            # and successfully bind the port itself
            manager.start_process(manager.terminal_configs[0])
            try:
                assert manager.is_process_running("/")
                assert wait_for_port(port), "manager ttyd did not start"
            finally:
                manager.stop()
        finally:
            # Ensure cleanup even if assertions fail
            if leftover.poll() is None:
                leftover.terminate()
                leftover.wait(timeout=5)


# =============================================================================
# Fix 3: installer integrity
# =============================================================================


class TestInstallerIntegrity:
    """Downloaded binaries must be digest-verified and never leave partial
    files behind on failure."""

    def test_verify_sha256_roundtrip(self, tmp_path):
        from terminaide.core.installer import verify_sha256

        import hashlib

        f = tmp_path / "blob"
        f.write_bytes(b"terminaide integrity test")
        digest = hashlib.sha256(b"terminaide integrity test").hexdigest()
        assert verify_sha256(f, digest)
        assert not verify_sha256(f, "0" * 64)

    def _download_to(self, tmp_path, content: bytes, digest: str = None):
        from terminaide.core import installer

        target = tmp_path / "ttyd-test"
        url = "https://example.invalid/ttyd"

        def fake_urlretrieve(url_arg, dest):
            Path(dest).write_bytes(content)

        orig = installer.urllib.request.urlretrieve
        installer.urllib.request.urlretrieve = fake_urlretrieve
        try:
            installer.download_binary(url, target, expected_digest=digest)
        finally:
            installer.urllib.request.urlretrieve = orig
        return target

    def test_download_verified_and_installed(self, tmp_path):
        import hashlib

        content = b"fake ttyd binary"
        digest = hashlib.sha256(content).hexdigest()
        target = self._download_to(tmp_path, content, digest)

        assert target.exists()
        assert target.read_bytes() == content
        assert target.stat().st_mode & 0o111, "binary must be executable"
        assert not target.with_name(target.name + ".download").exists()

    def test_download_with_wrong_digest_aborts_and_leaves_nothing(self, tmp_path):
        from terminaide.core import installer

        content = b"tampered binary"
        try:
            self._download_to(tmp_path, content, digest="f" * 64)
        except RuntimeError as e:
            assert "SHA-256" in str(e) or "verification" in str(e)
        else:
            pytest.fail("tampered download must be rejected")

        # Neither the binary nor a partial download may remain
        assert not (tmp_path / "ttyd-test").exists()
        assert not (tmp_path / "ttyd-test.download").exists()

    def test_pinned_version_constants(self):
        from terminaide.core.installer import (
            TTYD_PINNED_VERSION,
            TTYD_BINARY_DIGESTS,
            get_ttyd_version,
        )

        # Every pinned platform must have a known digest (64 hex chars)
        assert TTYD_PINNED_VERSION
        for key, digest in TTYD_BINARY_DIGESTS.items():
            assert len(digest) == 64, f"digest for {key} must be sha256 hex"
            int(digest, 16)
        # Custom version override changes the version (digests then skipped)
        import os

        old = os.environ.get("TERMINAIDE_TTYD_VERSION")
        try:
            os.environ["TERMINAIDE_TTYD_VERSION"] = "9.9.9"
            assert get_ttyd_version() == "9.9.9"
        finally:
            if old is None:
                os.environ.pop("TERMINAIDE_TTYD_VERSION", None)
            else:
                os.environ["TERMINAIDE_TTYD_VERSION"] = old


# =============================================================================
# Fix 4: health endpoint disclosure
# =============================================================================


class TestHealthEndpoint:
    """The default /health response must not disclose internals."""

    def test_health_minimal_by_default_and_verbose_via_env(self, tmp_path):
        import asyncio
        import os

        import httpx
        from fastapi import FastAPI

        import terminaide

        script = make_test_script(tmp_path)
        app = FastAPI()
        terminaide.serve_apps(app, {"/t": {"script": str(script)}}, log_level="warning")

        async def scenario():
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    # Default: minimal status only
                    r = await client.get("/health")
                    assert r.status_code == 200
                    assert r.json() == {"status": "ok"}

                    # Verbose via env override: full operational payload
                    os.environ["TERMINAIDE_HEALTH_VERBOSE"] = "1"
                    try:
                        r2 = await client.get("/health")
                        data = r2.json()
                        assert "proxy" in data and "ttyd" in data
                        routes = [
                            r
                            for r in data["proxy"]["routes"]
                            if r.get("type") == "terminal"
                        ]
                        assert len(routes) == 1
                    finally:
                        os.environ.pop("TERMINAIDE_HEALTH_VERBOSE", None)

        asyncio.run(scenario())

    def test_html_security_headers_present(self, tmp_path):
        import asyncio

        import httpx
        from fastapi import FastAPI

        import terminaide

        script = make_test_script(tmp_path)
        app = FastAPI()
        terminaide.serve_apps(app, {"/t": {"script": str(script)}}, log_level="warning")

        async def scenario():
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    r = await client.get("/t")
                    assert r.status_code == 200
                    assert r.headers["x-content-type-options"] == "nosniff"
                    assert r.headers["referrer-policy"] == "no-referrer"
                    assert r.headers["x-frame-options"] == "SAMEORIGIN"

        asyncio.run(scenario())


class TestProxyHeaderHygiene:
    """The proxy must not forward hop-by-hop headers or cookies to ttyd,
    but must keep Authorization (ttyd -c basic auth passes through)."""

    def test_excluded_request_headers(self):
        from terminaide.core.proxy import ProxyManager

        excluded = ProxyManager._EXCLUDED_REQUEST_HEADERS
        for header in (
            "host",
            "connection",
            "keep-alive",
            "proxy-authorization",
            "te",
            "trailer",
            "upgrade",
            "cookie",
        ):
            assert header in excluded, f"{header} must not be forwarded to ttyd"
        # Authorization is deliberately forwarded for ttyd -c credentials
        assert "authorization" not in excluded

    def test_trace_not_accepted(self):
        """The terminal proxy route must not accept TRACE."""
        import asyncio

        import httpx
        from fastapi import FastAPI

        import terminaide
        from pathlib import Path

        tmp = Path("/tmp/terminaide_trace_test")
        tmp.mkdir(exist_ok=True)
        script = make_test_script(tmp)
        app = FastAPI()
        terminaide.serve_apps(
            app, {"/t": {"script": str(script)}}, log_level="warning"
        )

        async def scenario():
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    r = await client.request("TRACE", "/t/terminal/token.js")
                    assert r.status_code == 405, "TRACE must be rejected"

        asyncio.run(scenario())


# =============================================================================
# Fix 6: per-connection parameter files
# =============================================================================


class TestPerConnectionParamFiles:
    """Dynamic-route parameters must be isolated per connection."""

    def test_write_query_params_file_unique_and_atomic(self, tmp_path):
        import json

        from terminaide.core.wrappers import write_query_params_file
        from terminaide.core.config import TerminaideConfig

        config = TerminaideConfig(ephemeral_cache_dir=tmp_path)

        f1 = write_query_params_file("/test", {"args": "--a"}, config)
        f2 = write_query_params_file("/test", {"args": "--b"}, config)

        # Unique files per connection, same route-scoped prefix
        assert f1 != f2
        assert f1.name.startswith("terminaide_params__test_")
        assert f2.name.startswith("terminaide_params__test_")
        # Both parse to their own content
        assert json.loads(f1.read_text())["params"]["args"] == "--a"
        assert json.loads(f2.read_text())["params"]["args"] == "--b"
        # No partial-write leftovers, restrictive permissions
        assert not list(tmp_path.joinpath("params").glob("*.tmp"))
        assert f1.stat().st_mode & 0o777 == 0o600

    def test_generated_wrapper_uses_atomic_claim(self, tmp_path):
        from terminaide.core.wrappers import generate_dynamic_wrapper_script

        script = make_test_script(tmp_path)
        content = generate_dynamic_wrapper_script(
            script_path=script,
            static_args=["--base"],
            python_executable="python",
            args_param="args",
            cache_dir=tmp_path,
        )

        # Claim queue, not a fixed filename
        assert "os.rename" in content
        assert "terminaide_params_{sanitized_route}_*.json" in content
        assert ".claimed" in content
        assert "FileNotFoundError" in content

        # The generated code must be syntactically valid
        compile(content, "dynamic_wrapper.py", "exec")

    def test_claim_logic_two_wrappers_never_share_a_file(self, tmp_path):
        """Simulate the generated wrapper's claim loop: two competing
        consumers must end up with distinct parameter files."""
        import json
        import os

        from terminaide.core.wrappers import write_query_params_file
        from terminaide.core.config import TerminaideConfig

        config = TerminaideConfig(ephemeral_cache_dir=tmp_path)
        f1 = write_query_params_file("/test", {"args": "--first"}, config)
        f2 = write_query_params_file("/test", {"args": "--second"}, config)

        def claim_like_wrapper(pid: int):
            """Mirror of the claim loop from generate_dynamic_wrapper_script."""
            pattern = "terminaide_params__test_*.json"
            for candidate in sorted(
                tmp_path.joinpath("params").glob(pattern),
                key=lambda p: p.stat().st_mtime,
            ):
                claim_target = candidate.with_name(
                    candidate.name + f".{pid}.claimed"
                )
                try:
                    os.rename(candidate, claim_target)
                    return claim_target
                except FileNotFoundError:
                    continue
            return None

        # First "wrapper" (pid 111) claims, second (pid 222) must get the other file
        w1 = claim_like_wrapper(111)
        w2 = claim_like_wrapper(222)

        assert w1 is not None and w2 is not None
        assert w1 != w2
        args1 = json.loads(w1.read_text())["params"]["args"]
        args2 = json.loads(w2.read_text())["params"]["args"]
        assert {args1, args2} == {"--first", "--second"}

        # Nothing left unclaimed
        assert not list(
            tmp_path.joinpath("params").glob("terminaide_params__test_*.json")
        )

    def test_cleanup_covers_all_param_file_states(self, tmp_path):
        import os
        import time

        from terminaide.core.wrappers import (
            write_query_params_file,
            cleanup_stale_param_files,
        )
        from terminaide.core.config import TerminaideConfig

        config = TerminaideConfig(ephemeral_cache_dir=tmp_path)
        fresh = write_query_params_file("/test", {}, config)
        # Simulate an in-flight write and a wrapper-claimed file
        in_flight = fresh.with_name("terminaide_params__test_x.json.tmp")
        in_flight.write_text("{}")
        claimed = fresh.with_name("terminaide_params__test_y.json.999.claimed")
        claimed.write_text("{}")
        # Make everything stale
        old = time.time() - 3600
        for f in (fresh, in_flight, claimed):
            os.utime(f, (old, old))

        cleanup_stale_param_files(max_age_seconds=300, config=config)

        assert not fresh.exists()
        assert not in_flight.exists()
        assert not claimed.exists()


# =============================================================================
# Fix 7: WebSocket rate limiting
# =============================================================================


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeWebSocket:
    def __init__(self, host="127.0.0.1"):
        self.client = _FakeClient(host)


class TestWebSocketRateLimit:
    """Per-IP WebSocket connection limiting (each WS connection spawns a
    ttyd child process - unauthenticated connection floods are trivial
    resource exhaustion without this)."""

    def _proxy(self, ws_rate_limit_per_minute=30, tmp_path=None):
        from terminaide.core.models import TTYDConfig
        from terminaide.core.proxy import ProxyManager

        config = TTYDConfig(
            port=free_port(),
            ws_rate_limit_per_minute=ws_rate_limit_per_minute,
            route_configs=[
                ScriptConfig(
                    route_path="/",
                    script=tmp_path / "hello.py",
                    port=free_port(),
                )
            ],
        )
        return ProxyManager(config)

    def test_allows_up_to_limit_then_blocks(self, tmp_path):
        (tmp_path / "hello.py").write_text("print(1)")
        proxy = self._proxy(ws_rate_limit_per_minute=3, tmp_path=tmp_path)

        assert proxy._check_ws_rate_limit(_FakeWebSocket("1.2.3.4"))
        assert proxy._check_ws_rate_limit(_FakeWebSocket("1.2.3.4"))
        assert proxy._check_ws_rate_limit(_FakeWebSocket("1.2.3.4"))
        assert not proxy._check_ws_rate_limit(_FakeWebSocket("1.2.3.4"))
        # Other IPs have their own budget
        assert proxy._check_ws_rate_limit(_FakeWebSocket("5.6.7.8"))

    def test_disabled_when_none(self, tmp_path):
        (tmp_path / "hello.py").write_text("print(1)")
        proxy = self._proxy(ws_rate_limit_per_minute=None, tmp_path=tmp_path)
        for _ in range(50):
            assert proxy._check_ws_rate_limit(_FakeWebSocket("1.2.3.4"))

    def test_integration_second_connection_rejected(self, tmp_path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        import terminaide

        script = make_test_script(tmp_path)
        app = FastAPI()
        terminaide.serve_apps(
            app,
            {"/t": {"script": str(script)}},
            log_level="warning",
            ws_rate_limit_per_minute=1,
        )

        with TestClient(app) as client:
            # First connection is allowed
            with client.websocket_connect("/t/terminal/ws"):
                pass
            # Second connection from the same client (same IP in tests) is
            # rejected with a close frame; surfaced by attempting to receive
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect("/t/terminal/ws") as ws2:
                    ws2.receive_text()
            assert exc_info.value.code == 1013