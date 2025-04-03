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

Terminaide offers two primary approaches: Single Terminal mode for quickly serving individual functions or scripts, and Multi Terminal mode for integrating multiple terminals into a FastAPI application. Start with Single mode for simplicity, then graduate to Multi mode when you need more flexibility.

### Solo Server 

The Solo Server provides the fastest way to web-enable a Python function or script. It creates a standalone web server with a single terminal and handles all the configuration details for you. Choose between Function mode or Script mode based on your use case.

#### Script Mode

The absolute simplest way to use Terminaide is to serve an existing Python script that you don't want to modify:

```python
from terminaide import serve_script

if __name__ == "__main__":
    serve_script("my_script.py")
```

#### Function Mode

However if you have even a **little** flexibility, you can serve a Python function directly from a single entry point. Just pass any Python function to `serve_function()` and it's instantly web-accessible: 

```python
from terminaide import serve_function

def hello():
    name = input("What's your name? ")
    print(f"Hello, {name}!")

if __name__ == "__main__":
    serve_function(hello)  # That's it!
```

#### Configuration Options

Both Function and Script modes accept these configuration options:

```python
# For serve_function(func, **kwargs) or serve_script(script_path, **kwargs)
kwargs = {
    # Server options
    "port": 8000,                # Web server port
    "title": None,               # Terminal title (auto-generated if not specified)
    "debug": True,               # Enable debug mode
    "reload": False,             # Enable auto-reload on code changes
    "trust_proxy_headers": True, # Trust X-Forwarded-Proto headers
    "template_override": None,   # Custom HTML template path
    
    # Terminal appearance
    "theme": {
        "background": "black",     # Background color
        "foreground": "white",     # Text color
        "cursor": "white",         # Cursor color
        "cursor_accent": None,     # Secondary cursor color
        "selection": None,         # Selection highlight color
        "font_family": None,       # Terminal font
        "font_size": None          # Font size in pixels
    },
    
    # TTYD process options
    "ttyd_options": {
        "writable": True,            # Allow terminal input
        "interface": "127.0.0.1",    # Network interface to bind
        "check_origin": True,        # Enforce same-origin policy
        "max_clients": 1,            # Maximum simultaneous connections
        "credential_required": False, # Enable authentication
        "username": None,            # Login username
        "password": None,            # Login password
        "force_https": False         # Force HTTPS mode
    },
    
    # Environment variable handling
    "forward_env": True,         # Forward all environment variables (default)
    # Alternative 1: "forward_env": False,  # Disable environment forwarding
    # Alternative 2: "forward_env": ["AWS_PROFILE", "PATH", "DJANGO_SETTINGS"],  # Specific variables
    # Alternative 3: "forward_env": {       # With selective overrides
    #     "AWS_PROFILE": "dev",   # Set specific value
    #     "DEBUG": "1",           # Set specific value
    #     "PATH": None            # Use value from parent process
    # }
}
```

### Apps Server

The Apps Server extends the capabilities of the Solo Server to integrate multiple terminals into an existing FastAPI application. This approach gives you more control over routing, allows multiple terminals to coexist with regular web endpoints, and provides additional configuration options.

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

#### Advanced Configuration

The Apps Server includes all the configuration options from the Solo Server, plus these additional options:

```python
serve_apps(
    # Required parameters
    app,                      # FastAPI application
    terminal_routes={         # Dictionary mapping paths to scripts
        # Basic format
        "/path1": "script1.py",
        
        # With arguments
        "/path2": ["script2.py", "--arg1", "value"],
        
        # Advanced configuration
        "/path3": {
            "client_script": "script3.py",
            "args": ["--mode", "advanced"],
            "title": "Custom Title",
            "port": 7682      # Specific port for this terminal
        }
    },
    
    # Additional multi-mode specific options
    mount_path="/",           # Base path for terminal mounting
    ttyd_port=7681,           # Base port for ttyd processes
    
    # Plus all options from single mode
    port=8000,
    title=None,
    debug=True,
    # etc.
)
```

### Examples

The `demo/` directory demonstrates these configurations with several ready-to-use demos:

```bash
poe serve              # Default mode with instructions
poe serve function     # Function mode - demo of serve_function()
poe serve script       # Script mode - demo of serve_script()
poe serve apps         # Apps mode - HTML page at root with multiple terminals
poe serve container    # Run in Docker container
```

### Pre-Requisites

- Python 3.12+
- Linux or macOS (Windows support on roadmap)
- macOS users need Xcode Command Line Tools (`xcode-select --install`)
- Docker/Poe for demos

## Limitations

Terminaide is designed to support rapid prototype deployments for small user bases. As a result:

- Not intended for high-traffic production environments
- Basic security features (though ttyd authentication is supported)
- Windows installation not yet supported
- Terminal capabilities limited to what ttyd provides

## License

MIT