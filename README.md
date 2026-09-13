<!-- # TERMINAIDE -->
<div align="center">
<pre>
████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗ █████╗ ██╗██████╗ ███████╗
╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║██╔══██╗██║██╔══██╗██╔════╝
   ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║███████║██║██║  ██║█████╗  
   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██╔══██║██║██║  ██║██╔══╝  
   ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║██║  ██║██║██████╔╝███████╗
   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝╚═════╝ ╚══════╝
</pre>

A Unix compatible, batteries-included Python library for serving CLI applications in a browser. 

Instantly web-enable terminal applications with as few as two lines of code.

![PyPI - Version](https://img.shields.io/pypi/v/terminaide) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/terminaide) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg) 

</div>

## How It Works

Terminaide builds on three core design principles:

- **Instant Web Enablement**: Any Python function or script becomes web-accessible without modification
- **Zero Infrastructure**: Self-contained with automatic ttyd management and single-port architecture for easy cloud/container deployment
- **Transparent Execution**: Preserves execution context (directory, environment variables, virtual environments) as if running locally

When you serve a Python function or script(s) with Terminaide, several things happen behind the scenes:

1. **Function Wrapping**: Functions are automatically wrapped in temporary scripts, allowing any Python callable to run in a terminal without modification.

2. **Unified Port Access**: A proxy layer routes both terminal and web traffic through a single port, with each terminal getting its own isolated backend process.

3. **Context Preservation**: Code runs from the appropriate working directory, maintaining relative imports and file paths as expected.

4. **Virtual Environment Detection**: Scripts automatically use their associated virtual environments (.venv, venv, Poetry environments) when available, isolating dependencies without manual configuration.

5. **Environment Inheritance**: Environment variables are automatically forwarded to terminal sessions, with optional customization.

6. **Resource Management**: All processes, temporary files, and connections are automatically created and cleaned up as needed.

## Security

Terminaide serves **interactive, writable shells** — so its defaults are built around a single principle: *unauthenticated terminals must be impossible by construction.*

### Default posture

- **Loopback everywhere**: `serve_script()`/`serve_function()` bind `127.0.0.1` (local-only), and every ttyd backend process binds loopback regardless — terminal traffic only ever flows through the proxy. Direct access to the ttyd ports from the network is impossible unless you opt in via `ttyd_options.interface`.
- **Exposure requires a token**: bind a non-loopback host (`host="0.0.0.0"`) without credentials and a session token is auto-generated, printed to the server console as a ready-to-click URL, and required on all terminal routes — the Jupyter model. Loopback-only servers stay frictionless (no token).
- **Verified binary**: the ttyd binary is downloaded from a pinned release with SHA-256 verification; unverified downloads are never installed.
- **Minimal disclosure**: `/health` returns `{"status": "ok"}` unless you opt into the full operational payload with `health_verbose=True` (or `TERMINAIDE_HEALTH_VERBOSE=1`).
- **Session isolation**: dynamic-route URL parameters are passed per-connection (never shared between sessions), WebSocket connections are rate-limited per client IP (30/min by default), and credential-looking environment variables inherited by unauthenticated terminals trigger a startup warning.

### Authentication options

```python
# Auto-generated token (default when exposed) - printed to the console:
serve_script("deploy.py", host="0.0.0.0")

# Your own token (also via TERMINAIDE_TOKEN env var):
serve_script("deploy.py", host="0.0.0.0", auth_token="my-secret")

# ttyd HTTP basic-auth credentials instead of a token:
serve_script("deploy.py", host="0.0.0.0",
            ttyd_options={"credential_required": True,
                          "username": "u", "password": "p"})

# Explicitly unauthenticated (loud warning; only behind your own auth or isolation):
serve_script("deploy.py", host="0.0.0.0", auth_token="")
```

A validated `?token=` is stored in an HttpOnly cookie, so menu navigation and terminal iframes work without the token in every URL. `X-Terminaide-Token` is accepted for programmatic clients. The token never reaches your terminal's `argv` or parameter files.

### File caches and other knobs

By default, Terminaide creates temporary files only within the package directory (`terminaide/cache/`). To use external directories, configure them explicitly:

```python
from terminaide import serve_function, TerminaideConfig

config = TerminaideConfig(
    ephemeral_cache_dir="/secure/cache",      # For temporary scripts
    monitor_log_path="/secure/logs/app.log"  # For monitor logs
)
serve_function(my_function, config=config)

# Or use environment variables
import os
os.environ["TERMINAIDE_CACHE_DIR"] = "/secure/cache"
os.environ["TERMINAIDE_MONITOR_LOG"] = "/secure/logs/app.log"
```

Other security-relevant options: `allow_embedding` (X-Frame-Options; terminals are clickjacking targets), `ws_rate_limit_per_minute` (None disables), and `forward_env` (scope the environment your terminals inherit — see the startup warning).

## Installation

Install it from PyPI via your favorite package manager:

```bash
pip install terminaide
# or
poetry add terminaide
```

Terminaide automatically installs and manages its own ttyd binary within the package — downloaded from a pinned release with SHA-256 verification — with no reliance on system-installed versions, to ensure a consistent, tamper-checked experience across environments:

- On Linux: Pre-built binaries are downloaded automatically
- On macOS: The binary is compiled from source (requires Xcode Command Line Tools `xcode-select --install`)

## Usage

Terminaide offers three types of Python servers: Script, Function and Apps.

### Script Server 

The absolute simplest way to use Terminaide is to serve an existing Python script that you don't want to modify. Scripts automatically use their associated virtual environments when available: 

```python
from terminaide import serve_script

serve_script("../other_project/client.py")  # Local-only: binds 127.0.0.1, open http://localhost:8000

# To expose to the network, bind explicitly — a session token is auto-generated
# and printed to the console (or set your own with auth_token=...):
serve_script("deploy.py", host="0.0.0.0")
```

### Function Server

If you want total self-containment, you can also pass any Python function to `serve_function()` and it's instantly accessible. Just make sure to wrap your imports in the function that you're serving: 

```python
from terminaide import serve_function

def hello():
    from rich.console import Console

    console = Console()

    name = input("What's your name? ")

    console.print(f"Hello, {name}!")
    
serve_function(hello)
```

### Apps Server

The Apps Server integrates multiple terminal routes into an existing FastAPI application, allowing you to serve scripts, functions, and index pages alongside regular web endpoints. The Apps Server requires a FastAPI `app` and `terminal_routes` dictionary (which is both functions and script compatible):

```python
import uvicorn
from fastapi import FastAPI
from terminaide import serve_apps

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Welcome to my app"}

def hello():
    name = input("What's your name? ")
    print(f"Hello, {name}!")

serve_apps(
    app,
    terminal_routes={
        "/script": "my_script.py",    # Script-based terminal
        "/hello": hello,              # Function-based terminal
        "/tool": {                    # Dynamic terminal with query params
            "script": "tool.py", 
            "dynamic": True,
            "args_param": "with"          # Use ?with=arg1,arg2 instead of ?args=arg1,arg2
        }
    },
    # host declares your app's bind for the auth decision: non-loopback + no
    # credentials => terminal routes get a token. Default "0.0.0.0" (assume
    # exposed); pass "127.0.0.1" for purely local apps to skip token auth.
    host="0.0.0.0",
    auth_token=None,   # or set a fixed token / TERMINAIDE_TOKEN env var
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

#### Config

All three serving functions accept the same configuration options, including command-line arguments via the `args` parameter and dynamic URL query parameters via `dynamic: True`. When `dynamic: True`, arguments can be passed via URL query parameters (e.g., `?args=--verbose,--output,file.txt`), with the parameter name customizable via `args_param`:


```python
{
    "port": 8000,                    # Web server port (default: 8000)
    "title": "My Terminal App",      # Terminal window title (default: auto-generated)
    "log_level": "info",             # Logging level: "debug", "info", "warning", "error", None (default: "info")
    "args": ["--verbose", "file.txt"], # Command-line arguments (default: None)
    "dynamic": True,                 # Enable URL query parameter arguments (default: False)
    "args_param": "args",            # Query parameter name for dynamic arguments (default: "args")
    "host": "127.0.0.1",            # Server bind / declared bind (loopback default for direct modes; "0.0.0.0" = exposed)
    "auth_token": None,              # Terminal token: None = auto (required when exposed), "" = disabled, "your-token" = fixed
    "health_verbose": False,        # Full operational payload in /health (default: minimal {"status": "ok"})
    "allow_embedding": False,       # Allow framing by other origins (X-Frame-Options)
    "ws_rate_limit_per_minute": 30, # Per-IP WebSocket connection limit (None = unlimited)
    
    # Keyboard mapping (CMD to CTRL on Mac)
    "keyboard_mapping": {
        "mode": "smart",             # "none" (default), "smart", "all", or "custom"
        "custom_mappings": {         # Override mappings when mode is "custom"
            "z": True,               # Map CMD+Z to CTRL+Z
            "arrowleft": True,       # Map CMD+Left to Home (beginning of line)
            "c": False,              # Don't map CMD+C (leave as system shortcut)
        }
    },
    
    "theme": {                       # Terminal appearance
        "background": "black",       # Background color (default: "black")
        "foreground": "white",       # Text color (default: "white")  
        "cursor": "white",           # Cursor color (default: "white")
        "cursor_accent": "#ff0000",  # Secondary cursor color (default: None)
        "selection": "#333333",      # Selection highlight color (default: None)
        "font_family": "monospace",  # Terminal font (default: None)
        "font_size": 14,             # Desktop font size in pixels (default: 18)
        "mobile_font_size": 10       # Mobile font size in pixels (default: 16)
    }
}
```

**Keyboard Mapping (Mac CMD → CTRL):**

On Mac, terminal applications expect CTRL+key shortcuts, but Mac users naturally use CMD+key. Terminaide provides intelligent keyboard mapping with **clipboard integration** for seamless copy/paste workflow:

```python
# Smart mode: Optimized defaults with clipboard sync
serve_script("my_app.py", keyboard_mapping={"mode": "smart"})
# Clipboard sync: CMD+C → browser copy + terminal CTRL+C (copy errors/logs)
# Paste: CMD+V → browser paste only (no double paste)
# Editing: CMD+Z/Y/X/S/F → terminal CTRL+key
# Navigation: CMD+arrows → terminal navigation (Home/End/CTRL+Home/CTRL+End)
# Browser shortcuts preserved: CMD+W/R/T (close/refresh/new tab)

# All mode: Maps all CMD combinations to terminal CTRL
serve_script("my_app.py", keyboard_mapping={"mode": "all"})

# Custom mode: Granular behavior control
serve_script("my_app.py", keyboard_mapping={
    "mode": "custom",
    "custom_mappings": {
        "c": "both",       # Copy: browser + terminal (clipboard sync)
        "v": "browser",    # Paste: browser only (clean paste)
        "a": "terminal",   # Select all: terminal CTRL+A (select all in terminal)
        "z": "terminal",   # Undo: terminal only
        "x": "both",       # Cut: browser + terminal (if desired)
        "arrowleft": "terminal",  # Navigation: terminal only
        # Behavior options: "both", "browser", "terminal", or omit to disable
    }
})

**Clipboard Integration Strategy:**

The keyboard mapping system intelligently handles clipboard operations to provide the best user experience:

- **`"both"`**: Browser action + terminal signal (ideal for CMD+C to copy terminal output AND send interrupt)
- **`"browser"`**: Browser action only (ideal for CMD+V paste and CMD+A select all)  
- **`"terminal"`**: Terminal signal only (traditional mapping, blocks browser action)
- **Omitted keys**: No mapping (preserves browser shortcuts like CMD+W, CMD+T)

This approach ensures clipboard sync between browser and terminal while avoiding conflicts and double actions.

**Backward Compatibility:**

Existing configurations using boolean values (`True`/`False`) are automatically converted:
- `True` → `"terminal"` (terminal-only behavior)
- `False` → `"none"` (no mapping)

```python
# Legacy format (still works)
keyboard_mapping={"mode": "custom", "custom_mappings": {"c": True, "w": False}}
# Equivalent to:
keyboard_mapping={"mode": "custom", "custom_mappings": {"c": "terminal"}}

# In Apps Server with per-route configuration
serve_apps(app, {
    "/editor": {
        "script": "editor.py",
        "keyboard_mapping": {"mode": "smart"}
    }
})
```

**Dynamic Arguments Usage Examples:**

```python
# Default parameter name (uses ?args=...)
serve_script("cli.py", dynamic=True)
# Visit: http://localhost:8000?args=--verbose,--output,result.txt

# Custom parameter name (uses ?with=...)
serve_script("cli.py", dynamic=True, args_param="with")
# Visit: http://localhost:8000?with=--verbose,--output,result.txt

# In Apps Server
serve_apps(app, {
    "/tool": {
        "script": "tool.py",
        "dynamic": True,
        "args_param": "params"  # Uses ?params=...
    }
})
```

Additionally, the Apps Server accepts several options for managing multiple terminals, routing, and FastAPI integration. You can pass these as keyword arguments to `serve_apps()` or bundle them in a `TerminaideConfig` object for reusability.

```python
{
    # Apps Mode Specific Parameters
    "ttyd_port": 7681,                     # Base port for ttyd processes
    "mount_path": "/",                     # Base path for terminal mounting  
    "preview_image": "default.png",        # Default preview image for social media
    "template_override": "custom.html",    # Custom HTML template file
    "trust_proxy_headers": True,           # Trust proxy headers for authentication
    
    # Cache Configuration (Security)
    "ephemeral_cache_dir": "/custom/cache", # Override for ephemeral script storage (default: package cache)
    "monitor_log_path": "/custom/logs/monitor.log", # Override for monitor log file location (default: package cache)
    
    # TTYD Process Options
    "ttyd_options": {
        "writable": True,                  # Allow terminal input
        "interface": "0.0.0.0",           # Bind interface
        "check_origin": True,              # Check WebSocket origin
        "max_clients": 1,                  # Maximum concurrent clients per terminal
        "credential_required": False,      # Require authentication
        "username": None,                  # Authentication username
        "password": None,                  # Authentication password
        "force_https": False               # Force HTTPS connections
    }
}
```

### Utilities 

Terminaide also includes a few utilities for turning your Apps Server into a fully functional, stylish website in pure Python.

#### Auto Index

AutoIndex creates navigable menu pages with ASCII art titles and keyboard navigation using pure Python. It provides a unified API that renders as either a web page or terminal interface based on the `type` parameter.

```python
{
    "type": "html" | "curses",  # Required: rendering mode
    "menu": [...],              # Required: flat list of menu items
    "title": "MY APP",          # Title text (default: 'Index')
    "subtitle": "Welcome!",     # Text below title
    "instructions": "Navigate", # Menu instruction text
    "epititle": "...",          # Text/link below menu (see below)
    "supertitle": "v1.0",       # Text above title
    "preview_image": "img.png"  # Preview image path (HTML only)
}
```

The `epititle` parameter can be configured in three ways:
- **Plain text**: `epititle="Server status: OK"`
- **Terminal route**: `epititle={"path": "/monitor", "title": "Server Monitor", "function": monitor_func}`
- **External link**: `epititle={"url": "https://github.com", "title": "View on GitHub", "new_tab": True}`

In HTML mode, AutoIndex can automatically create terminal routes from menu items that contain functions or scripts, eliminating the need to define routes twice:

```python
from terminaide import AutoIndex, serve_apps

def calculator():
    print("Calculator running...")

def editor():
    print("Editor running...")

# HTML mode with automatic route extraction
serve_apps(app, {
    "/": AutoIndex(
        type="html",
        title="Developer Tools",
        menu=[
            # These create both menu items AND terminal routes
            {"path": "/calc", "title": "Calculator", "function": calculator},
            {"path": "/edit", "title": "Editor", "function": editor, "keyboard_mapping": {"mode": "smart"}},
            {"path": "/logs", "title": "View Logs", "script": "logs.py"},
            {"path": "https://docs.python.org", "title": "Python Docs", "new_tab": True}
        ],
        # Epititle can also define a terminal route
        epititle={"path": "/monitor", "title": "Server Monitor", "function": monitor_func}
    )
})
# Creates: index page at "/" plus terminals at "/calc", "/edit", "/logs", and "/monitor"
```

In Curses mode, AutoIndex creates an interactive terminal menu that directly executes functions or scripts when selected. Menu items can reference functions, scripts, or Python module paths:

```python
# Curses mode for direct terminal execution
curses_menu = AutoIndex(
    type="curses", 
    title="CLI TOOLS",
    menu=[
        {"function": calculator, "title": "Calculator"},
        {"script": "editor.py", "title": "Text Editor"}
    ],
    instructions="Arrow keys to navigate"
)

# Serve the curses menu as a terminal route
serve_apps(app, {
    "/": curses_menu,  # Interactive menu accessible at root
})

# Or run directly in terminal
curses_menu.show()
```

#### Server Monitor

If you want real time visibility into your terminal applications, `ServerMonitor` wraps your process to capture all output while still displaying it normally. Create a ServerMonitor instance to start logging, then use `ServerMonitor.read()` in another terminal to view logs with a rich interface featuring scrolling, colors, and keyboard navigation.

```python
from terminaide import serve_apps, ServerMonitor
from fastapi import FastAPI

def my_app():
    ServerMonitor(title="My App")
    print("Hello from monitored app!")

serve_apps(FastAPI(), {
    "/app": my_app,
    "/logs": ServerMonitor.read
})
```

#### TerminASCII 

Terminaide uses the `terminascii()` function to generate stylized ASCII art banners from text. This built-in utility creates decorative headers and titles using the "ansi-shadow" font, perfect for adding visual appeal to terminal applications:

```python
from terminaide import terminascii

# Generate ASCII art banner
banner = terminascii("HELLO WORLD")
print(banner)
```

## Terminarcade

The `examples/` directory contains working examples that demonstrate all Terminaide features. These serve as both development tests and usage examples:

```
poe serve-function      # Function mode - demo of serve_function()
poe serve-script        # Script mode - demo of serve_script()
poe serve-apps          # Apps mode - HTML page at root with multiple terminals
poe spin                # Run in Docker container (requires Docker Desktop)
```

Explore the demo source code to see advanced usage patterns and implementation examples.

## Cloud & Container Deployment

Terminaide is cloud-ready when: **token auth on, ttyd loopback (default), TLS in front, IMDSv2 on the box.** Concretely:

### The checklist

1. **Terminate TLS in front.** Put an ALB / nginx / CloudFlare in front of the app and pass `trust_proxy_headers=True` so generated URLs and cookie flags respect `X-Forwarded-Proto`. Never serve terminals over plain HTTP across a network — keystrokes (including passwords typed into CLIs) and the session token travel in cleartext otherwise.
2. **Pin your token for scripted deployments.** Auto-generated tokens are great for humans; for containers and CI, set `TERMINAIDE_TOKEN` so the URL is deterministic. For Docker, the token appears in `docker logs`:

   ```bash
   docker run -p 8000:8000 -e TERMINAIDE_TOKEN=my-token terminaide
   # then open http://localhost:8000/?token=my-token
   ```

3. **Security group: one port.** Only the app port (443/8000) needs to be open. The ttyd backends are loopback-bound by default — the historical footgun of opening a 7681+ port range is structurally gone. Never open port ranges.
4. **On EC2: enable IMDSv2** (hop limit 1) and attach a **least-privilege IAM role**. A writable terminal means the terminal user can reach the instance metadata service — scope the role as if the terminal user will read its credentials, because they can.
5. **Scope the environment.** Terminals inherit the server's environment (`forward_env=True` by default — that's the contract: your scripts, your environment). The startup warning names credential-looking variables; pass `forward_env=["PATH", "HOME", "MY_TOOL_API_KEY"]` to hand terminals only what they need.
6. **Monitor with `health_verbose=True`** behind your own auth if you want the full operational payload (per-route ports, process health, and the active auth token) — the public `/health` stays minimal by default.

### Topology

```
Internet → ALB (TLS) → terminaide (FastAPI, one port)
                        ├─ token-auth middleware
                        └─ proxy → ttyd backends (127.0.0.1 only) → your scripts
```

### A note on trust models

Serving **yourself** your own tools over the internet (token-authenticated) is the supported cloud use case. Serving terminals to **untrusted public users** is a different threat model: anyone typing at the terminal is executing commands as the server user. If you go there, plan for sandboxing, per-session credentials, and input validation — treat it as a separate product tier, not a configuration.

## Integrations

Terminaide pairs well with:

- [Ngrok](https://github.com/ngrok/ngrok-python) for exposing local terminal sessions to remote users securely. 
- [Lazy Beanstalk](https://github.com/basileaw/lazy-beanstalk) for simple cloud deployments to AWS Elastic Beanstalk.

