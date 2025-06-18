<!-- # TERMINAIDE -->
```
████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗ █████╗ ██╗██████╗ ███████╗
╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║██╔══██╗██║██╔══██╗██╔════╝
   ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║███████║██║██║  ██║█████╗  
   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██╔══██║██║██║  ██║██╔══╝  
   ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║██║  ██║██║██████╔╝███████╗
   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝╚═════╝ ╚══════╝
```

A handy Python library for serving CLI applications in a browser. Terminaide allows developers to instantly web-enable Python CLIs without packaging or distribution overhead, making it ideal for prototypes, demos, and applications with small user bases.

![PyPI - Python Version](https://img.shields.io/pypi/pyversions/terminaide) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg) ![PyPI - Version](https://img.shields.io/pypi/v/terminaide) 

## How It Works

Terminaide builds on three core design principles:

- **Instant Web Enablement**: Any Python function or script becomes web-accessible without modification
- **Zero Infrastructure**: Self-contained with automatic ttyd management and single-port architecture for easy cloud/container deployment
- **Transparent Execution**: Preserves execution context (directory, environment variables) as if running locally

When you serve a Python function or script with Terminaide, several things happen behind the scenes:

1. **Ephemeral Script Generation**: For functions passed to `serve_function()`, Terminaide creates a temporary Python wrapper script that imports and executes your function. This allows any Python callable to run in a terminal without modification.

2. **Single-Port Architecture**: Terminaide implements a proxy layer that routes both WebSocket (terminal) and HTTP (web) traffic through a single port. The ttyd process runs on a dynamically allocated internal port, while the proxy handles all external communication. In Apps mode, each terminal route gets its own ttyd instance with automatic port assignment.

3. **Execution Context Preservation**: Scripts run from their containing directory, maintaining relative imports and file access. Functions run from the caller's directory. File paths are resolved relative to the caller's context, not Terminaide's installation directory.

4. **Environment Variable Forwarding**: By default, all environment variables from the parent process are forwarded to the terminal session. You can optionally specify which variables to forward or override specific values.

5. **Lifecycle Management**: Terminaide uses AsyncContext managers to handle the complex lifecycle of ttyd processes, temporary files, and proxy connections. All resources are automatically cleaned up when the server stops.

## Installation

Install it from PyPI via your favorite package manager:

```bash
pip install terminaide
# or
poetry add terminaide
```

Terminaide automatically installs and manages its own ttyd binary within the package, with no reliance on system-installed versions, to ensure a consistent experience across environments and simplified setup and cleanup:

- On Linux: Pre-built binaries are downloaded automatically
- On macOS: The binary is compiled from source (requires Xcode Command Line Tools `xcode-select --install`)

Unfortunately, Windows is not currently supported :(

## Usage

Terminaide offers two primary approaches: Solo Mode for quickly serving individual functions, scripts, or servers, and Apps Mode for integrating multiple terminals into a FastAPI application. Start with Solo Mode for simplicity, then graduate to Apps Mode when you need multiple terminals in one application.

### Solo Server

The Solo Server provides the fastest way to web-enable a Python function or script. It creates a standalone web server with a single terminal and handles all the configuration details for you. Choose between Function or Script Server based on your use case.

#### Scripts

The absolute simplest way to use Terminaide is to serve an existing Python script that you don't want to modify:

```python
from terminaide import serve_script

if __name__ == "__main__":
    serve_script("my_script.py")

```

#### Functions

Serve a Python function directly from a single entry point. Just pass any Python function to `serve_function()` and it's instantly accessible: 

```python
from terminaide import serve_function

def hello():
    name = input("What's your name? ")
    print(f"Hello, {name}!")

if __name__ == "__main__":
    serve_function(hello)

```

#### Solo Server Config

Both `serve_function()` and `serve_script()` accept the same optional configuration arguments:

```python
{
    "port": 8000,                    # Web server port (default: 8000)
    "title": "My Terminal App",      # Terminal window title (default: auto-generated)
    "theme": {                       # Terminal appearance
        "background": "black",       # Background color (default: "black")
        "foreground": "white",       # Text color (default: "white")
        "cursor": "white",           # Cursor color (default: "white")
        "cursor_accent": "#ff0000",  # Secondary cursor color (default: None)
        "selection": "#333333",      # Selection highlight color (default: None)
        "font_family": "monospace",  # Terminal font (default: None)
        "font_size": 14              # Font size in pixels (default: None)
    }
}
```

For advanced configuration like authentication, environment variables, or custom templates, use `serve_apps()` instead.

### Apps Server

The Apps Server extends terminaide's capabilities to integrate multiple terminals into an existing FastAPI application. This approach gives you more control over routing, allows multiple terminals to coexist with regular web endpoints, and provides additional configuration options.

You can use both functions and scripts in your terminal routes:

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
        "/hello": hello               # Function-based terminal
    }
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

#### Apps Mode Config

The Apps Server integrates multiple terminal routes into an existing FastAPI application, allowing you to serve scripts, functions, and index pages alongside regular web endpoints. The Apps Server requires a FastAPI `app` and `terminal_routes` dictionary, accepts all of the same arguments as the Solo Server functions, plus additional options for managing multiple terminals, routing, and FastAPI integration. You can pass these as keyword arguments to `serve_apps()` or bundle them in a `TerminaideConfig` object for reusability.

```python
{
    # Apps Mode Specific Parameters
    "ttyd_port": 7681,                     # Base port for ttyd processes
    "mount_path": "/",                     # Base path for terminal mounting  
    "preview_image": "default.png",        # Default preview image for social media
    "template_override": "custom.html",    # Custom HTML template file
    "trust_proxy_headers": True,           # Trust proxy headers for authentication
    "configure_logging": True,             # Configure Terminaide's logging handlers
    
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

#### Index Objects

If you want to create navigation pages for your terminal routes using pure Python instead of HTML templates, Index Objects provide menu systems with ASCII art titles and keyboard navigation.

The `HtmlIndex` menu accepts paths that can be either internal terminal routes or external URLs, allowing you to mix terminal applications with regular web links in the same menu:

```python
from terminaide import HtmlIndex

index = HtmlIndex(
    title="MY APP",
    menu=[{
        "label": "Resources",
        "options": [
            {"path": "/terminal", "title": "My App"},     # Internal terminal route
            {"path": "https://docs.python.org", "title": "Python Docs"}  # External URL
        ]
    }]
)
```
In contrast, the `CursesIndex` requires each menu item to specify either a Python function or script to execute, since it runs in a terminal environment where web navigation isn't possible. This allows the CurseIndex to function outside of a web browser if a pure CLI is preferred:

```python
from terminaide import CursesIndex

def calc_app():
    # Calculator implementation
    pass

index = CursesIndex(
    title="MY APP",
    menu=[{
        "label": "Tools",
        "options": [
            {"path": "/calc", "title": "Calculator", "function": calc_app},
            {"path": "/edit", "title": "Editor", "script": "editor.py"}
        ]
    }]
)
``` 

Otherwise, both accept the same optional args:

```python
{
    "title": "MY APP",          # Title text (default: 'Index')
    "subtitle": "Welcome!",     # Text below title
    "epititle": "Press Enter",  # Text below menu
    "supertitle": "v1.0",       # Text above title
    "preview_image": "img.png"  # Preview image path
}
```

#### Server Monitor

If you want real time visibility into your terminal applications, `Monitor` wraps your process to capture all output while still displaying it normally. Create a Monitor instance to start logging, then use `Monitor.read()` in another terminal to view logs with a rich interface featuring scrolling, colors, and keyboard navigation.

```python
from terminaide import Monitor

monitor = Monitor(title="My Server")
# Your app runs normally, all output captured
app.run()

# In another terminal:
Monitor.read()  # Interactive log viewer
```

#### Termin_Ascii 

Terminaide uses the `termin_ascii()` function to generate stylized ASCII art banners from text. This built-in utility creates decorative headers and titles using the "ansi-shadow" font, perfect for adding visual appeal to terminal applications:

```python
from terminaide import termin_ascii

# Generate ASCII art banner
banner = termin_ascii("HELLO WORLD")
print(banner)
```

## Termin-Arcade Demo

The `demo/` directory contains working examples that demonstrate all Terminaide features. These serve as both development tests and usage examples:

```
make serve              # Default mode with instructions
make serve function     # Function mode - demo of serve_function()
make serve script       # Script mode - demo of serve_script()
make serve apps         # Apps mode - HTML page at root with multiple terminals
make serve container    # Run in Docker container (requires Docker Desktop)
```

Explore the demo source code to see advanced usage patterns and implementation examples.

## Disclaimer

Terminaide is designed to support rapid prototype deployments for small user bases. It's not intended for high-traffic production environments and provides only basic security (via TTYD authentication). If deploying, it is highly recommended that you implement appropriate security measures for your environment, such as proper authentication, network isolation, and access controls. 

