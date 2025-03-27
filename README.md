# Terminaide

A handy Python library for serving CLI applications in a browser. Terminaide allows developers to instantly web-enable terminal-based Python applications without packaging or distribution overhead, making it ideal for prototypes, demos, and applications with small user bases.

## How It Works

Terminaide builds on three core technical elements:

1. **ttyd Management**: Automatically handles the installation and lifecycle of ttyd (terminal over WebSocket) binaries for the current platform. This eliminates the need for manual ttyd configuration.

2. **Single-Port Proxying**: Routes all HTTP and WebSocket traffic through a single port, simplifying deployments in containers and cloud environments while maintaining cross-origin security.

3. **FastAPI Integration**: Seamlessly integrates with FastAPI applications, allowing terminals to coexist with traditional web pages and REST endpoints via flexible route prioritization.

## Installation

Install it from PyPI via your favorite package manager:

```bash
pip install terminaide
# or
poetry add terminaide
```

Terminaide automatically installs and manages its own ttyd binary within the package, with no reliance on system-installed versions:
- On Linux: Pre-built binaries are downloaded automatically
- On macOS: The binary is compiled from source (requires Xcode Command Line Tools)

This approach ensures a consistent experience across environments and simplifies both setup and cleanup.

## Usage

Terminaide offers three API entry points with increasing levels of complexity and flexibility:

### 1. Function Mode (Simplest)

The absolute simplest way to serve a Python function directly in a browser terminal:

```python
from terminaide import serve_function

def hello():
    name = input("What's your name? ")
    print(f"Hello, {name}!")

if __name__ == "__main__":
    serve_function(hello)  # That's it!
```

Just pass any Python function to `serve_function()` and it's instantly web-accessible. No servers to configure, no special code to write.

### 2. Script Mode (Simple)

To serve an existing Python script file:

```python
from terminaide import serve_script

if __name__ == "__main__":
    serve_script("my_script.py")
```

This approach is ideal when you have an existing terminal application that you don't want to modify. Your script runs exactly as it would in a normal terminal, but becomes accessible through any web browser.

### 3. Apps Mode (Advanced)

To integrate multiple terminals into a FastAPI application:

```python
from fastapi import FastAPI
from terminaide import serve_apps
import uvicorn

app = FastAPI()

# Custom routes defined first take precedence
@app.get("/")
async def root():
    return {"message": "Welcome to my terminal app"}

serve_apps(
    app,
    terminal_routes={
        "/cli1": "script1.py",
        "/cli2": ["script2.py", "--arg1", "value"],
        "/cli3": {
            "client_script": "script3.py",
            "title": "Advanced CLI"
        }
    }
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

This approach works best when you're building a new application with terminaide from the start, especially when you need to combine web interfaces with multiple terminal applications under different routes.

### Configuration Options

The following configuration options are available for the advanced `serve_apps()` function:

```python
serve_apps(
    app,                      # FastAPI application
    terminal_routes={...},    # Dictionary mapping paths to scripts
    mount_path="/",           # Base path for terminal mounting
    port=7681,                # Base port for ttyd processes
    theme=None,               # Terminal theme (colors, fonts)
    ttyd_options=None,        # Options for ttyd processes
    template_override=None,   # Custom HTML template
    title="Terminal",         # Default terminal title
    debug=False,              # Enable debug mode
    trust_proxy_headers=True  # Trust X-Forwarded-Proto headers
)
```

The **terminal_routes** dictionary supports these formats:

- Basic format: `"/path": "script.py"`
- With arguments: `"/path": ["script.py", "--arg1", "value"]`
- Advanced: `"/path": {"client_script": "script.py", "args": [...], "title": "Title", "port": 7682}`

For theme and ttyd customization, you can use:

#### Theme Options

```python
theme={
    "background": "black",      # Background color
    "foreground": "white",      # Text color
    "cursor": "white",          # Cursor color
    "cursor_accent": None,      # Secondary cursor color
    "selection": None,          # Selection highlight color
    "font_family": None,        # Terminal font
    "font_size": None           # Font size in pixels
}
```

#### TTYD Options

```python
ttyd_options={
    "writable": True,            # Allow terminal input
    "interface": "127.0.0.1",    # Network interface to bind
    "check_origin": True,        # Enforce same-origin policy
    "max_clients": 1,            # Maximum simultaneous connections
    "credential_required": False, # Enable authentication
    "username": None,            # Login username
    "password": None,            # Login password
    "force_https": False         # Force HTTPS mode
}
```

The simpler `serve_function()` and `serve_script()` functions accept a subset of these options: `port`, `title`, `theme`, and `debug`.

### Examples

The `demo/` directory demonstrates these configurations with several ready-to-use demos:

```bash
poe serve              # Default mode with instructions
poe serve function     # Function mode - demo of serve_function()
poe serve script       # Script mode - demo of serve_script()
poe serve apps         # Apps mode - HTML page at root with multiple terminals
poe serve container    # Run in Docker container
```

## Pre-Requisites

- Python 3.12+
- Linux or macOS (Windows support on roadmap)
- macOS users need Xcode Command Line Tools (`xcode-select --install`)
- Docker/Poe for demos

## Limitations

Terminaide is designed to support rapid prototype deployments for small user bases. As a result:

- Not intended for high-traffic production environments
- Basic security features (though ttyd authentication is supported)
- Windows installation not yet supported (on roadmap)
- Terminal capabilities limited to what ttyd provides

## License

MIT