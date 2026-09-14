"""
Tests for terminaide utilities: terminascii, ServerMonitor, and AutoIndex.

These cover the utility API surface that the demos exercise end-to-end:
- terminascii: ASCII banner generation (#146)
- ServerMonitor: log-file lifecycle and safe usage inside monitored
  processes (#141). Note: ServerMonitor re-execs the calling script under
  a pty unless MONITORED_PROCESS is set - tests set it to exercise the
  in-monitored-process behavior, which is the real usage pattern inside
  served terminal apps.
- AutoIndex: menu parsing, route extraction, and the curses-menu-to-
  terminal-route integration (#142).
"""

from pathlib import Path

import pytest

from terminaide import AutoIndex, terminascii
from terminaide.core.index import AutoMenuItem
from terminaide.core.monitor import ServerMonitor, _resolve_monitor_log_path
from terminaide.core.models import create_route_configs, ScriptConfig


# =============================================================================
# terminascii (#146)
# =============================================================================


class TestTerminascii:
    def test_banner_is_multiline_ascii_art(self):
        banner = terminascii("HELLO")
        assert banner, "expected generated banner"
        assert "\n" in banner, "banner should be multiline"
        assert "█" in banner, "ansi-shadow font uses block characters"
        # Trailing whitespace is stripped by contract
        assert banner == banner.rstrip()

    def test_roundtrip_shape_stable(self):
        # Same input produces consistent output
        assert terminascii("A") == terminascii("A")

    def test_empty_input_returns_none(self):
        assert terminascii("") is None


# =============================================================================
# ServerMonitor (#141)
# =============================================================================


class TestServerMonitor:
    def test_init_inside_monitored_process(self, tmp_path, monkeypatch):
        """ServerMonitor used inside an already-monitored process (the real
        usage inside served terminal apps): sets up state, no re-exec."""
        monkeypatch.setenv("MONITORED_PROCESS", "1")
        log = tmp_path / "monitor.log"
        m = ServerMonitor(output_file=str(log), title="TEST")
        assert m.output_file == str(log)

    def test_default_title_used(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MONITORED_PROCESS", "1")
        m = ServerMonitor(output_file=str(tmp_path / "log.txt"))
        assert m.output_file.endswith("log.txt")

    def test_read_is_static_callable(self):
        # ServerMonitor.read is the terminal-side reader entry point
        assert callable(getattr(ServerMonitor, "read", None))

    def test_log_path_resolution_honors_explicit_path(self, tmp_path):
        log_path = tmp_path / "custom" / "app.log"
        resolved = _resolve_monitor_log_path(log_path)
        assert Path(resolved) == log_path

    def test_log_path_resolution_defaults_to_cache(self):
        resolved = _resolve_monitor_log_path()
        assert str(resolved).endswith("monitor.log")


# =============================================================================
# AutoIndex (#142)
# =============================================================================


def make_fn():
    """A terminal-runnable function for menu items."""

    def my_tool():
        print("running")

    return my_tool


class TestAutoIndex:
    def test_html_template_context(self):
        idx = AutoIndex(
            type="html",
            title="MY MENU",
            subtitle="sub",
            menu=[
                {"path": "/a", "title": "A"},
                {"path": "/b", "title": "B", "new_tab": True},
            ],
        )
        assert idx.index_type == "html"
        ctx = idx.to_template_context()
        assert ctx["page_title"] == "MY MENU"
        items = ctx["menu_items"]
        assert {i["path"] for i in items} == {"/a", "/b"}

    def test_extract_routes_from_menu_items(self):
        fn = make_fn()
        idx = AutoIndex(
            type="html",
            title="MENU",
            menu=[
                {"path": "/tool", "title": "Tool", "function": fn},
                {"path": "/logs", "title": "Logs", "script": "logs.py"},
                # External URLs are menu links, not terminal routes
                {"path": "https://example.com", "title": "Docs", "new_tab": True},
            ],
        )
        routes = idx.extract_routes()
        assert set(routes) == {"/tool", "/logs"}
        assert routes["/tool"]["function"] is fn
        assert routes["/logs"]["script"] == "logs.py"
        assert "https://example.com" not in routes

    def test_invalid_type_rejected(self):
        with pytest.raises(ValueError):
            AutoIndex(type="pdf", menu=[])

    def test_get_all_menu_items(self):
        idx = AutoIndex(
            type="html",
            title="MENU",
            menu=[
                {"path": "/a", "title": "A"},
                {"path": "/b", "title": "B"},
            ],
        )
        items = idx.get_all_menu_items()
        assert len(items) == 2
        assert all(isinstance(i, AutoMenuItem) for i in items)

    def test_curses_menu_becomes_terminal_route(self):
        """The headline integration: a curses AutoIndex is served through
        ttyd as a navigable terminal (arrow keys, Enter to select)."""
        fn = make_fn()
        curses_menu = AutoIndex(
            type="curses",
            title="CLI TOOLS",
            menu=[
                {"path": "/calc", "title": "Calc", "function": fn},
            ],
        )
        route_configs = create_route_configs({"/menu": curses_menu})
        assert len(route_configs) == 1
        cfg = route_configs[0]
        assert isinstance(cfg, ScriptConfig)
        assert cfg.is_function_based, "curses menu must be a terminal route"
        assert cfg.function_object is not None

    def test_html_menu_with_route_extraction_in_server(self):
        """Menus can define terminal routes inline (no double definition):
        menu items with functions/scripts become routes automatically."""
        fn = make_fn()
        idx = AutoIndex(
            type="html",
            title="Developer Tools",
            menu=[
                {"path": "/calc", "title": "Calculator", "function": fn},
                {"path": "/logs", "title": "Logs", "script": "logs.py"},
            ],
        )
        # extract_routes is what serve_apps feeds into route creation
        routes = idx.extract_routes()
        assert set(routes) == {"/calc", "/logs"}
