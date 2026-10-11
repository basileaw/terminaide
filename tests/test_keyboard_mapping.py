"""Enhanced-keyboard (Shift+Enter) behavior and its supporting JS module.

Shift+Enter is the one modified key browsers cannot express without a
keyboard protocol: xterm.js sends CR for both Enter and Shift+Enter. The
protocol logic lives in ``terminaide/static/keyboard_protocol.js`` so it
can be exercised directly with Node (CI images ship Node; the test skips
where it is missing). The template wiring tests keep the module and the
template from drifting apart.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from terminaide.core.models import KeyboardMappingConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_JS = REPO_ROOT / "terminaide" / "static" / "keyboard_protocol.js"
TERMINAL_TEMPLATE = REPO_ROOT / "terminaide" / "templates" / "terminal.html"

NODE = shutil.which("node")


# =============================================================================
# Per-route behavior contract (what the template sends to the browser)
# =============================================================================


def test_smart_mode_does_not_map_enter():
    """Smart mode must leave Shift+Enter alone; only enhanced protocols or
    an explicit "enter" mapping may intercept it."""
    cfg = KeyboardMappingConfig(mode="smart")
    assert cfg.get_key_behavior("enter") == "none"
    assert cfg.should_map_key("enter") is False


def test_custom_enter_maps_to_terminal():
    cfg = KeyboardMappingConfig(mode="custom", custom_mappings={"enter": "terminal"})
    assert cfg.get_key_behavior("enter") == "terminal"


def test_custom_enter_browser_opts_out():
    cfg = KeyboardMappingConfig(mode="custom", custom_mappings={"enter": "browser"})
    assert cfg.get_key_behavior("enter") == "browser"


# =============================================================================
# Protocol module (unit-tested through Node)
# =============================================================================


def test_protocol_module_ships_with_the_package():
    source = PROTOCOL_JS.read_text(encoding="utf-8")
    assert "__terminaideKeyboardProtocol" in source
    assert "createWatcher" in source


def test_terminal_template_inlines_protocol_module():
    html = TERMINAL_TEMPLATE.read_text(encoding="utf-8")
    assert "keyboard-protocol-data" in html
    assert "keyboard_protocol_js" in html
    assert "protocol.shiftEnterSequence" in html


@pytest.mark.skipif(NODE is None, reason="node is required for the JS unit tests")
def test_protocol_logic_with_node():
    script = r"""
const assert = require('assert');
const mod = require(__MODULE__);

// --- toText -----------------------------------------------------------------
assert.strictEqual(mod.toText('abc'), 'abc');
assert.strictEqual(mod.toText(new TextEncoder().encode('\x1b[?u')), '\x1b[?u');
assert.strictEqual(mod.toText(new TextEncoder().encode('hi').buffer), 'hi');
assert.strictEqual(mod.toText(42), null);

// --- no negotiation ---------------------------------------------------------
let w = mod.createWatcher();
assert.strictEqual(w.shiftEnterSequence('none'), null);
assert.strictEqual(w.shiftEnterSequence(undefined), null);
assert.strictEqual(w.shiftEnterSequence('browser'), null);
assert.strictEqual(w.shiftEnterSequence('terminal'), '\n');

// --- Kitty query (pi's startup output): CSI-u, even without route config ---
w = mod.createWatcher();
w.sniff('\x1b[>7u\x1b[?u\x1b[c');
assert.strictEqual(w.state.kitty, true);
assert.strictEqual(w.shiftEnterSequence('none'), '\x1b[13;2u');
assert.strictEqual(w.shiftEnterSequence('terminal'), '\x1b[13;2u');
assert.strictEqual(w.shiftEnterSequence('browser'), null);

// --- query split across writes ----------------------------------------------
w = mod.createWatcher();
w.sniff('\x1b[>7u\x1b');
w.sniff('[?u');
assert.strictEqual(w.state.kitty, true);
assert.strictEqual(w.shiftEnterSequence('none'), '\x1b[13;2u');

// --- modifyOtherKeys --------------------------------------------------------
w = mod.createWatcher();
w.sniff('\x1b[>4;2m');
assert.strictEqual(w.state.modifyOtherKeys, true);
assert.strictEqual(w.shiftEnterSequence('none'), '\x1b[27;2;13~');

w = mod.createWatcher();
w.sniff('\x1b[>4;1m');
assert.strictEqual(w.state.modifyOtherKeys, true);

// --- Kitty wins when both were requested ------------------------------------
w = mod.createWatcher();
w.sniff('\x1b[>4;2m');
w.sniff('\x1b[>7u\x1b[?u');
assert.strictEqual(w.shiftEnterSequence('none'), '\x1b[13;2u');

// --- ordinary output never flips the flags ----------------------------------
w = mod.createWatcher();
w.sniff('hello world\x1b[0m\r\n');
assert.strictEqual(w.state.kitty, false);
assert.strictEqual(w.state.modifyOtherKeys, false);
assert.strictEqual(w.shiftEnterSequence('none'), null);

console.log('keyboard_protocol.js: all assertions passed');
""".replace("__MODULE__", json.dumps(str(PROTOCOL_JS)))

    result = subprocess.run(
        [NODE, "-e", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, (result.stdout + result.stderr)
