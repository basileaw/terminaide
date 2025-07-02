# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Practical Usage

Usage, tenets and value proposition are covered in @README.md.

## Common Development Commands

The development commands are defined in @Makefile.

## Architecture Overview

### Core Design Pattern: Proxy-Based Terminal Management
Terminaide uses a reverse proxy architecture where each terminal runs as a separate ttyd process, and a central ProxyManager routes HTTP/WebSocket traffic to the appropriate instance.

### Key Components

1. **API Layer** (`terminaide/termin_api.py`): Public API with three entry points
   - `serve_function()`: Wraps Python functions as terminal apps
   - `serve_script()`: Serves Python scripts directly
   - `serve_apps()`: Integrates terminals into existing FastAPI apps

2. **Application Factory** (`terminaide/core/factory.py`): Creates FastAPI apps with lifecycle management
   - Handles reload mode with environment serialization
   - Generates ephemeral wrappers for functions

3. **TTYd Manager** (`terminaide/core/ttyd_manager.py`): Terminal process lifecycle
   - Port allocation and conflict resolution
   - Health monitoring and automatic restarts
   - Cleanup of zombie processes
   - Virtual environment detection and Python executable resolution

4. **Proxy System** (`terminaide/core/proxy.py`): HTTP/WebSocket reverse proxy
   - Path prefix stripping and protocol handling
   - Bidirectional WebSocket forwarding

5. **Configuration** (`terminaide/core/models.py`, `terminaide/core/config.py`): 
   - Pydantic-based validation
   - Multi-level configuration with inheritance
   - Smart defaults and path resolution
   - Unified `log_level` parameter across all API functions

6. **Virtual Environment Utils** (`terminaide/core/venv_utils.py`): Environment detection
   - Automatic detection of .venv, venv, env directories
   - Poetry project support (pyproject.toml + .venv)
   - Search from script directory upward to project root

7. **Wrapper System** (`terminaide/core/wrappers.py`): Unified wrapper script generation
   - Function wrappers: Generate ephemeral Python scripts for wrapping functions and scripts
   - Dynamic wrappers: Generate scripts that accept runtime arguments via temp files
   - Performance optimized with intelligent caching (LRU cache, directory caching, signature caching)
   - Unified cleanup and file management for all wrapper types

### Request Flow
```
Client → FastAPI → ProxyManager → TTYd Process → Python Script
         ↓                ↓
    Terminal HTML    WebSocket/HTTP
```

### Important Design Decisions

1. **Process Isolation**: Each terminal runs in separate ttyd process for better isolation
2. **Ephemeral Scripts**: Functions wrapped in temporary scripts for uniform handling
   - Dual cleanup strategy: graceful shutdown cleanup + startup safety net
   - Process-specific file tracking prevents naming conflicts with real packages
3. **Configuration Inheritance**: Multi-level config system (TerminaideConfig → TTYDConfig → ScriptConfig)
4. **Single Port Architecture**: All traffic through one port, proxy handles routing
5. **Virtual Environment Isolation**: Scripts automatically use their associated virtual environments for dependency isolation
6. **Dynamic Arguments**: Routes can accept command-line arguments via query parameters when configured with `dynamic: true`

### Testing Strategy
- Tests verify all three serving modes
- Checks for HTTP errors and Python tracebacks
- Validates ttyd process startup and WebSocket connectivity
- Docker tests skipped if Docker unavailable
- Uses `DemoProcess` helper for lifecycle management

### Development Notes
- Python 3.12+ required
- Uses Poetry for dependencies
- Custom task runner (tools/tasks.py) wraps all Make commands
- No linting tools configured - code formatting is manual
- Environment variables loaded from .env if present
- PYTHONPATH automatically includes project root