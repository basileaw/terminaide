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
from fastapi import FastAPI
from terminaide import serve_terminal
import uvicorn

app = FastAPI()
serve_terminal(app, client_script="my_script.py")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

This approach is ideal when you have an existing terminal application that you don't want to modify. Your script runs exactly as it would in a normal terminal, but becomes accessible through any web browser.

### Multi Mode

To serve multiple terminals in a more complex application:

```python
# app.py
from fastapi import FastAPI
from terminaide import serve_terminal
import uvicorn

app = FastAPI()

# Custom routes defined first take precedence
@app.get("/")
async def root():
    return {"message": "Welcome to my terminal app"}

serve_terminal(
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

Terminaide additionally provides a number of configuration options:

```python
serve_terminal(
    app,
    mount_path="/app",               # Base path (default: "/")
    port=7681,                       # Base port for ttyd (default: 7681)
    theme={                          # Terminal theme
        "background": "black",
        "foreground": "white", 
    },
    ttyd_options={                   # ttyd-specific options
        "credential_required": True,
        "username": "user",
        "password": "pass",
    },
    title="My Terminal App",         # Custom title
    debug=True                       # Debug mode
)
```

### Examples

The `example/` directory demonstrates these configurations with several ready-to-use examples:

```bash
poe serve              # Default mode with instructions
poe serve single       # Single application mode
poe serve multi        # Multi-terminal mode with HTML menu
poe serve container    # Run in Docker container
```

## Pre-Requisites

- Python 3.12+
- Linux or macOS (Windows support on roadmap)
- Docker/Poe for examples

## Limitations

Terminaide is designed to support rapid prototype deployments for small user bases. As a result:

- Not intended for high-traffic production environments
- Basic security features (though ttyd authentication is supported)
- Windows installation not yet supported (on roadmap)
- Terminal capabilities limited to what ttyd provides

## License

MIT