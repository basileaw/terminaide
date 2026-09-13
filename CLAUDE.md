# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Practical Usage

Usage, tenets and value proposition are covered in @README.md.

## Common Development Commands

The development commands are defined in @tasks.yaml using poethepoet.

## Architecture Overview

### Core Design Pattern: Proxy-Based Terminal Management
Terminaide uses a reverse proxy architecture where each terminal runs as a separate ttyd process, and a central ProxyManager routes HTTP/WebSocket traffic to the appropriate instance.

### Key Components

1. **API Layer** (`terminaide/__init__.py`): Public API with three entry points
   - `serve_function()`: Wraps Python functions as terminal apps
   - `serve_script()`: Serves Python scripts directly
   - `serve_apps()`: Integrates terminals into existing FastAPI apps
   - All functions support `args_param` for configurable dynamic argument parameter names

2. **Application Factory** (`terminaide/core/factory.py`): Creates FastAPI apps with lifecycle management
   - Handles reload mode with environment serialization
   - Generates ephemeral wrappers for functions

3. **TTYd Manager** (`terminaide/core/terminal.py`): Terminal process lifecycle
   - Port allocation and conflict resolution
   - Health monitoring
   - Safe cleanup of leftover ttyd processes (never kills foreign processes)
   - Virtual environment detection and Python executable resolution

4. **Proxy System** (`terminaide/core/proxy.py`): HTTP/WebSocket reverse proxy
   - Path prefix stripping and protocol handling
   - Bidirectional WebSocket forwarding

5. **Configuration** (`terminaide/core/models.py`, `terminaide/core/config.py`): 
   - Pydantic-based validation
   - Multi-level configuration with inheritance
   - Smart defaults and path resolution
   - Unified `log_level` parameter across all API functions

6. **Virtual Environment Utils** (`find_venv_python` in `terminaide/core/terminal.py`): Environment detection
   - Automatic detection of .venv, venv, env directories
   - Poetry project support (pyproject.toml + .venv)
   - Search from script directory upward to project root

7. **Wrapper System** (`terminaide/core/wrappers.py`): Unified wrapper script generation
   - Function wrappers: Generate ephemeral Python scripts for wrapping functions and scripts
   - Dynamic wrappers: Generate scripts that accept runtime arguments via parameter files
   - Performance optimized with intelligent caching (LRU cache, directory caching, signature caching)
   - Unified cleanup and file management for all wrapper types
   - Security: Requires explicit configuration for external file creation

8. **Keyboard Mapping System** (`terminaide/core/models.py`, `terminaide/templates/terminal.html`): CMD→CTRL mapping for Mac users
   - Configuration via `KeyboardMappingConfig` model with multiple modes
   - AutoIndex menu items can specify keyboard mapping for route extraction
   - Client-side JavaScript injection into ttyd iframe for event interception
   - Event dispatching to `.xterm-helper-textarea` and fallback elements

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
   - Parameter names configurable via `args_param` for semantic URLs
7. **Security-First File Management**: Files created only within package cache by default
   - External file creation requires explicit configuration (`ephemeral_cache_dir`, `monitor_log_path`)
   - Environment variable overrides: `TERMINAIDE_CACHE_DIR`, `TERMINAIDE_MONITOR_LOG`
   - Clear error messages guide users when configuration is needed

8. **Keyboard Mapping with Clipboard Integration**: Intelligent CMD→CTRL translation for Mac UX
   - Configuration model supports Union[bool, str] for granular behavior control per key
   - Four behavior types: "terminal", "browser", "both", "none"
   - Template receives behavior map via JSON for client-side event handling
   - JavaScript injection intercepts events and dispatches synthetic keyboard events to xterm input handler

9. **Curses AutoIndex Support**: Curses menus served through ttyd in browser
   - `AutoIndex(type="curses")` automatically wrapped as terminal function
   - Menu navigation happens in single ttyd session (arrow keys, Enter to select)
   - Games/apps launch in-place and return to menu on exit
   - Works seamlessly in Docker containers alongside HTML menus

10. **Security-First Defaults** (see `tests/test_security.py` for the enforced behavior):
    - ttyd processes bind `127.0.0.1` by default; only the proxy talks to them. `ttyd_options.interface` overrides binding, `TTYDOptions.connect_host` resolves wildcard binds for dialing
    - Port conflicts never SIGKILL foreign processes: only leftover ttyd processes spawned from the terminaide-managed binary are killed; anything else raises a clear `TTYDStartupError`
    - ttyd version pinned (`TTYD_PINNED_VERSION`) with embedded SHA-256 digests; downloads verified atomically; source tarballs extracted with tarfile's `data` filter
    - `/health` returns `{"status": "ok"}` by default; full payload via `health_verbose=True` or `TERMINAIDE_HEALTH_VERBOSE=1`
    - Proxy strips hop-by-hop headers and cookies (keeps Authorization for ttyd `-c`); HTML pages carry nosniff/Referrer-Policy/X-Frame-Options with embedding opt-in via `allow_embedding=True`
    - Dynamic-route parameters are per-connection files (uuid suffix, atomic write) consumed via an atomic FIFO claim queue in the generated wrapper — no cross-session leakage
    - Per-IP WebSocket connection rate limiting (`ws_rate_limit_per_minute`, default 30, `None` disables)
    - Unauthenticated terminals inheriting credential-looking env vars produce a startup warning (names only); scope with `forward_env=[...]`

11. **Terminal Token Authentication** (`terminaide/core/auth.py`):
    - Terminal routes require a token whenever the server is exposed beyond loopback and no other auth is configured (auto-generated, printed as a ready-to-click URL)
    - Precedence: explicit `auth_token` > `TERMINAIDE_TOKEN` env > auto-generation; `auth_token=""` explicitly disables (loud warning); ttyd `-c` credentials also satisfy auth
    - Direct modes (`serve_script`/`serve_function`) bind `127.0.0.1` by default (`host=` to change) - local dev stays frictionless; `serve_apps` declares its host (`host="0.0.0.0"` default = conservative)
    - Token accepted via `?token=`, `X-Terminaide-Token` header, or `terminaide_token` cookie; validated cookie issued on first query-token success so menus/iframes/WebSockets work without tokens in every URL
    - Index pages and `/health` stay public; the token never reaches terminal argv/parameter files

### Testing Strategy
- Tests verify all three serving modes
- Checks for HTTP errors and Python tracebacks
- Validates ttyd process startup and WebSocket connectivity
- Docker tests skipped if Docker unavailable
- Uses `DemoProcess` helper for lifecycle management

### Development Notes
- Python 3.12+ required
- Uses Poetry for dependencies
- Task runner uses poethepoet (poe) defined in @tasks.yaml
- No linting tools configured - code formatting is manual
- Environment variables loaded from .env if present
- PYTHONPATH automatically includes project root
- **Docker builds**: `.dockerignore` is symlinked to `.gitignore` to prevent architecture mismatches
  - The `terminaide/cache/` directory contains platform-specific ttyd binaries
  - If copied into Docker builds, Mac binaries cause "Exec format error" on Linux containers
  - Excluding cache forces runtime download of correct Linux binary via `installer.py`