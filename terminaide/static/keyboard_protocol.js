/*
 * Terminaide enhanced-keyboard protocol helpers.
 *
 * xterm.js (as bundled by ttyd) cannot tell Shift+Enter from Enter and
 * cannot negotiate an enhanced keyboard protocol. Apps that want modified
 * keys announce it on stdout, so terminaide watches the terminal output for:
 *
 *   \x1b[>Nu\x1b[?u  Kitty keyboard protocol: set flags / query support
 *   \x1b[>4;2m       xterm modifyOtherKeys mode 2
 *
 * Once an app has asked, Shift+Enter is answered with the sequence that app
 * parses. This module is DOM-free on purpose so it can be unit-tested with
 * Node (see tests/test_keyboard_protocol_js.py).
 */
(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
    } else {
        root.__terminaideKeyboardProtocol = factory();
    }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    var KITTY_PROTOCOL = /\x1b\[(?:\?|>)[0-9;]*u/;
    var MODIFY_OTHER_KEYS = /\x1b\[>4;[12]m/;
    // Longest sequence we match is ~8 chars; keep a generous tail so
    // sequences split across writes still match.
    var TAIL_LENGTH = 16;

    function toText(data) {
        if (typeof data === "string") return data;
        if (typeof TextDecoder === "undefined") return null;
        try {
            if (data instanceof Uint8Array) return new TextDecoder().decode(data);
            if (data instanceof ArrayBuffer) {
                return new TextDecoder().decode(new Uint8Array(data));
            }
        } catch (e) {
            return null;
        }
        return null;
    }

    function createWatcher() {
        var state = { kitty: false, modifyOtherKeys: false, tail: "" };

        return {
            state: state,

            /** Feed raw terminal output; flips flags when the app asks. */
            sniff: function (data) {
                var text = toText(data);
                if (text === null || text === "") return;
                var combined = state.tail + text;
                if (KITTY_PROTOCOL.test(combined)) state.kitty = true;
                if (MODIFY_OTHER_KEYS.test(combined)) state.modifyOtherKeys = true;
                state.tail = combined.slice(-TAIL_LENGTH);
            },

            /**
             * Bytes to send for Shift+Enter, or null to let the key through.
             * `enterBehavior` is the per-route config: "terminal" opts into
             * the legacy CTRL+J fallback, "browser" opts out of emulation.
             */
            shiftEnterSequence: function (enterBehavior) {
                if (enterBehavior === "browser") return null;
                if (state.kitty) return "\x1b[13;2u";
                if (state.modifyOtherKeys) return "\x1b[27;2;13~";
                if (enterBehavior === "terminal") return "\n";
                return null;
            },
        };
    }

    return { createWatcher: createWatcher, toText: toText };
});
