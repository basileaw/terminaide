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

### Disclaimer

Terminaide is designed for rapid prototyping with small user bases, not high-traffic production. It provides basic security via TTYD authentication. For deployments, implement proper authentication, network isolation, and access controls.

## Installation

Install it from PyPI via your favorite package manager:

```bash
pip install terminaide
# or
poetry add terminaide
```

Terminaide automatically installs and manages its own ttyd binary (using latest version available on GitHub) within the package, with no reliance on system-installed versions, to ensure a consistent experience across environments and simplified setup and cleanup:

- On Linux: Pre-built binaries are downloaded automatically
- On macOS: The binary is compiled from source (requires Xcode Command Line Tools `xcode-select --install`)

## Usage

Terminaide offers three types of Python servers: Script, Function and Apps.

### Script Server 

The absolute simplest way to use Terminaide is to serve an existing Python script that you don't want to modify. Scripts automatically use their associated virtual environments when available: 

```python
from terminaide import serve_script

serve_script("../other_project/client.py")  # Uses ../other_project/.venv if present
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
            "dynamic": True
        }
    }
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

#### Config

Serve_script, serve_function and terminal_routes all accept the following optional configuration arguments:

```python
{
    "port": 8000,                    # Web server port (default: 8000)
    "title": "My Terminal App",      # Terminal window title (default: auto-generated)
    "log_level": "info",             # Logging level: "debug", "info", "warning", "error", None (default: "info")
    "args": ["--verbose", "file.txt"], # Command-line arguments (default: None)
    "dynamic": True,                 # Enable URL query parameter arguments (default: False)
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

However, terminal_routes also supports additional per-route configuration options including command-line arguments and dynamic parameter passing. Individual
routes can specify args for static command-line arguments and dynamic: True to accept additional arguments via URL query parameters.

```python
  terminal_routes = {
      "/tool": {
          "script": "tool.py",
          "args": ["--config", "base.json"],  # Static arguments always passed
          "dynamic": True                     # Enable query parameter support
      }
  }
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

AutoIndex creates navigable menu pages with ASCII art titles and keyboard navigation using pure Python instead of HTML templates. It provides a unified API that can render either as a web page or terminal interface based on the `type` parameter.

```python
{
    "type": "html" | "curses",  # Required: rendering mode
    "menu": [...],              # Required: menu structure (groups and options)
    "title": "MY APP",          # Title text (default: 'Index')
    "subtitle": "Welcome!",     # Text below title
    "epititle": "Press Enter",  # Text below menu
    "supertitle": "v1.0",       # Text above title
    "preview_image": "img.png"  # Preview image path (HTML only)
}
```

The key difference is how the `path` field in menu options is interpreted: HTML mode expects URLs or routes, while Curses mode expects functions, scripts, or module paths for direct execution.

```python
from terminaide import AutoIndex

# HTML mode - creates web page with clickable links
html_index = AutoIndex(
    type="html",
    title="MY APP",
    menu=[{
        "label": "Resources",
        "options": [
            {"path": "/terminal", "title": "Terminal App"},
            {"path": "https://docs.python.org", "title": "Python Docs"}
        ]
    }]
)

# Curses mode - creates terminal menu that executes functions/scripts
def calculator():
    print("Calculator app running...")

curses_index = AutoIndex(
    type="curses", 
    title="MY APP",
    menu=[{
        "label": "Tools",
        "options": [
            {"function": calculator, "title": "Calculator"},
            {"script": "editor.py", "title": "Text Editor"}
        ]
    }]
)

# Use in Apps Mode
serve_apps(app, {"/": html_index, "/cli": curses_index})

# Or run Curses mode directly
curses_index.show()
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

The `tryit/` directory contains working examples that demonstrate all Terminaide features. These serve as both development tests and usage examples:

```
make serve function     # Function mode - demo of serve_function()
make serve script       # Script mode - demo of serve_script()
make serve apps         # Apps mode - HTML page at root with multiple terminals
make serve container    # Run in Docker container (requires Docker Desktop)
```

Explore the demo source code to see advanced usage patterns and implementation examples.

## Integrations

Terminaide pairs well with:

- [Ngrok](https://github.com/ngrok/ngrok-python) for exposing local terminal sessions to remote users securely. 
- [Lazy Beanstalk](https://github.com/basileaw/lazy-beanstalk) for simple cloud deployments to AWS Elastic Beanstalk.

