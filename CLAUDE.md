# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development
- `make serve` - Run the demo server with default configuration
- `make serve function` - Run demo in function mode
- `make serve script` - Run demo in script mode
- `make serve apps` - Run demo in apps mode
- `make serve container` - Run demo in Docker container

### Release
- `make release` - Release a new version (handles version bumping and publishing)

### Testing
No test suite is currently configured. Manual testing is done via the demo application.

## Architecture Overview

Terminaide is a Python library that serves terminal applications through web browsers or desktop windows. It wraps the ttyd terminal emulator and provides a clean Python API.

### Core Components

1. **API Entry Points** (`termin_api.py`):
   - `serve_function()` - Serves a Python function in a terminal
   - `serve_script()` - Serves a Python script file
   - `serve_apps()` - Integrates multiple terminals into FastAPI
   - `meta_serve()` - Runs servers that themselves serve terminals

2. **Application Factory** (`app_factory.py`):
   - Creates FastAPI applications based on serving mode
   - Manages desktop mode via pywebview
   - Generates ephemeral wrapper scripts for functions

3. **TTYD Management** (`ttyd_manager.py`):
   - Installs and manages ttyd binary lifecycle
   - Handles port allocation and process monitoring
   - Platform-specific binary management (download on Linux, compile on macOS)

4. **Proxy System** (`proxy.py`):
   - Routes WebSocket and HTTP traffic through single port
   - Handles authentication and header management
   - Implements streaming for large responses

### Key Design Patterns

- **Single Port Architecture**: All traffic (HTTP + WebSocket) goes through one port
- **Ephemeral Scripts**: Functions are wrapped in temporary Python scripts
- **Factory Pattern**: Applications created based on configuration
- **Lifecycle Management**: AsyncContext managers handle cleanup
- **Smart Path Resolution**: Scripts resolved relative to caller context

### Environment Variables

The library intelligently forwards environment variables:
- Default: Forward all environment variables
- Can specify list of variables to forward
- Can override specific values while forwarding others

### Directory Context

When serving scripts or functions, Terminaide preserves the directory context:
- Scripts run from their containing directory
- Functions run from the caller's directory
- Meta-serve maintains proper working directories

### Common Development Tasks

When modifying the codebase:
1. The demo application (`demo/server.py`) is the primary test harness
2. Use `reload=True` for development to enable hot reloading
3. Desktop mode requires pywebview and is not available in Apps mode
4. TTYD binaries are stored in `terminaide/core/bin/`

### Platform Support

- Linux: Pre-built ttyd binaries downloaded automatically
- macOS: ttyd compiled from source (requires Xcode CLI tools)
- Windows: Not yet supported

### Error Handling

Custom exceptions in `exceptions.py`:
- `TTYDNotFoundError` - ttyd binary issues
- `TTYDInstallationError` - Installation failures
- `ProxyConnectionError` - Connection problems
- `ProxyAuthenticationError` - Auth failures