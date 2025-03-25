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

Terminaide automatically installs the ttyd binary if not already present, simplifying setup for both novice users and containerized deployments without requiring system-level dependencies.

## Usage

There are two primary ways to use terminaide, depending on your needs:

### Single Script

To serve a single Python script with the absolute bare minimum overhead:

```python
# app.py
from terminaide import simple_serve

if __name__ == "__main__":
    simple_serve("my_script.py")
```

This approach is ideal when you have an existing terminal application that you don't want to modify. Your script runs exactly as it would in a normal terminal, but becomes accessible through any web browser.

### Multi Mode

To serve multiple terminals in a more complex application:

```python
# app.py
from fastapi import FastAPI
from terminaide import serve_terminals
import uvicorn

app = FastAPI()

# Custom routes defined first take precedence
@app.get("/")
async def root():
    return {"message": "Welcome to my terminal app"}

serve_terminals(
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

Terminaide supports the following configuration options when calling `serve_terminals()`:

- **terminal_routes** (required): Dictionary mapping URL paths to scripts
  - Basic format: `"/path": "script.py"`
  - With arguments: `"/path": ["script.py", "--arg1", "value"]`
  - Advanced: `"/path": {"client_script": "script.py", "args": [...], "title": "Title", "port": 7682}`

- **mount_path** (default: "/"): Base path where terminal will be mounted

- **port** (default: 7681): Base port for ttyd processes

- **theme**: Terminal appearance customization
  - `background`: Background color (default: "black")
  - `foreground`: Text color (default: "white")
  - `cursor`: Cursor color
  - `cursor_accent`: Secondary cursor color
  - `selection`: Selection highlight color
  - `font_family`: Terminal font
  - `font_size`: Font size in pixels

- **ttyd_options**: Options passed to the ttyd process
  - `writable` (default: True): Allow terminal input
  - `interface` (default: "127.0.0.1"): Network interface to bind
  - `check_origin` (default: True): Enforce same-origin policy
  - `max_clients` (default: 1): Maximum simultaneous connections
  - `credential_required` (default: False): Enable authentication
  - `username`: Login username (required if credential_required=True)
  - `password`: Login password (required if credential_required=True)
  - `force_https` (default: False): Force HTTPS mode

- **template_override**: Path to custom terminal HTML template

- **title** (default: "Terminal"): Title for the terminal window

- **debug** (default: False): Enable debug mode with detailed logging

- **trust_proxy_headers** (default: True): Trust X-Forwarded-Proto for HTTPS detection

### Examples

The `demo/` directory demonstrates these configurations with several ready-to-use demos:

```bash
poe serve              # Default mode with instructions
poe serve single       # Single application mode
poe serve multi        # Multi-terminal mode with HTML menu
poe serve container    # Run in Docker container
```

## Pre-Requisites

- Python 3.12+
- Linux or macOS (Windows support on roadmap)
- Docker/Poe for demos

## Limitations

Terminaide is designed to support rapid prototype deployments for small user bases. As a result:

- Not intended for high-traffic production environments
- Basic security features (though ttyd authentication is supported)
- Windows installation not yet supported (on roadmap)
- Terminal capabilities limited to what ttyd provides

## License

MIT