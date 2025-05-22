# app_factory.py

"""
Factory functions and app builders for Terminaide serving modes.

This module contains implementation classes that handle different serving modes
(function, script, apps, meta) and the factory functions used with Uvicorn's reload feature.
"""

import os
import sys
import time
import signal
import inspect
import logging
import uvicorn
import tempfile
import subprocess
import webview
import requests
from pathlib import Path
from fastapi import FastAPI
from typing import Callable, Optional
from contextlib import asynccontextmanager

from .app_config import (
    TerminaideConfig,
    convert_terminaide_config_to_ttyd_config,
    terminaide_lifespan,
    smart_resolve_path,
)

logger = logging.getLogger("terminaide")


def inline_source_code_wrapper(func: Callable) -> Optional[str]:
    """
    Attempt to inline the source code of 'func' if it's in __main__ or __mp_main__.
    Return the wrapper code as a string, or None if we can't get source code.
    """
    try:
        source_code = inspect.getsource(func)
    except OSError:
        return None

    func_name = func.__name__
    return f"""# Ephemeral inline function from main or mp_main
{source_code}
if __name__ == "__main__":
    {func_name}()"""


def generate_function_wrapper(func: Callable) -> Path:
    """
    Generate an ephemeral script for the given function. If it's in a real module,
    we do the normal import approach. If it's in __main__ or __mp_main__, inline fallback.
    """
    import inspect

    func_name = func.__name__
    module_name = getattr(func, "__module__", None)

    temp_dir = Path(tempfile.gettempdir()) / "terminaide_ephemeral"
    temp_dir.mkdir(exist_ok=True)
    script_path = temp_dir / f"{func_name}.py"

    # Determine the original source directory of the function
    try:
        source_file = inspect.getsourcefile(func) or inspect.getfile(func)
        source_dir = os.path.dirname(os.path.abspath(source_file))
    except Exception:
        source_dir = os.getcwd()  # fallback to current dir if all else fails

    # Inject original source dir and cwd into sys.path
    bootstrap = (
        "import sys, os\n"
        f'sys.path.insert(0, r"{source_dir}")\n'
        "sys.path.insert(0, os.getcwd())\n\n"
    )

    # If it's a normal module (not main or mp_main)
    if module_name and module_name not in ("__main__", "__mp_main__"):
        wrapper_code = (
            f"# Ephemeral script for function {func_name} from module {module_name}\n"
            f"{bootstrap}"
            f"from {module_name} import {func_name}\n"
            f'if __name__ == "__main__":\n'
            f"    {func_name}()"
        )
        script_path.write_text(wrapper_code, encoding="utf-8")
        return script_path

    # Inline fallback (if __main__ or dynamically defined)
    try:
        source_code = inspect.getsource(func)
        wrapper_code = (
            f"# Inline wrapper for {func_name} (from __main__ or dynamic)\n"
            f"{bootstrap}"
            f"{source_code}\n"
            f'if __name__ == "__main__":\n'
            f"    {func_name}()"
        )
        script_path.write_text(wrapper_code, encoding="utf-8")
        return script_path
    except Exception:
        # Last resort: static error fallback
        script_path.write_text(
            f'print("ERROR: cannot reload function {func_name} from module={module_name}")\n',
            encoding="utf-8",
        )
        return script_path


def generate_meta_script_wrapper(
    script_path: Path, app_dir: Optional[Path] = None
) -> Path:
    """
    Generate an ephemeral script that runs a server script with correct path resolution
    without changing the working directory. This preserves the original working directory
    for file operations while ensuring imports and script resolution work correctly.

    Args:
        script_path: The server script to wrap
        app_dir: The application directory (if None, will use the script's directory)

    Returns:
        Path to the generated wrapper script
    """
    script_name = script_path.stem

    temp_dir = Path(tempfile.gettempdir()) / "terminaide_ephemeral"
    temp_dir.mkdir(exist_ok=True)
    wrapper_script_path = temp_dir / f"meta_script_{script_name}.py"

    # Determine app directory if not provided
    if app_dir is None:
        app_dir = script_path.parent
        logger.debug(f"Using script directory as app_dir: {app_dir}")

    # Handle if app_dir is provided as a string
    if isinstance(app_dir, str):
        app_dir = Path(app_dir)

    # Generate the path injection code
    bootstrap = (
        "import sys, os\n"
        "from pathlib import Path\n"
        "import subprocess\n"
        "# Preserve original working directory for file operations\n"
        "original_cwd = os.getcwd()\n"
        f'app_dir = r"{app_dir}"\n'
        f'script_path = r"{script_path}"\n'
        "# Add paths to ensure imports work correctly\n"
        "if app_dir not in sys.path:\n"
        "    sys.path.insert(0, app_dir)\n"
        "if original_cwd not in sys.path:\n"
        "    sys.path.insert(0, original_cwd)\n"
        "# Monkey-patch sys.argv[0] to point to a file in the app directory\n"
        "# This ensures ScriptConfig validation resolves paths correctly\n"
        f'sys.argv[0] = str(Path(app_dir) / "main.py")\n\n'
        "# Override desktop mode to prevent infinite loops\n"
        "# Patch terminaide functions to force desktop=False in subprocess\n"
        "import terminaide.termin_api as termin_api\n"
        "original_meta_serve = termin_api.meta_serve\n"
        "def patched_meta_serve(*args, **kwargs):\n"
        "    kwargs['desktop'] = False  # Force web mode in subprocess\n"
        "    return original_meta_serve(*args, **kwargs)\n"
        "termin_api.meta_serve = patched_meta_serve\n\n"
        "# Execute the script using subprocess to maintain proper context\n"
        "try:\n"
        f"    result = subprocess.run([sys.executable, script_path], check=True)\n"
        "except subprocess.CalledProcessError as e:\n"
        f'    print(f"Error running script {script_path}: {{e}}")\n'
        "    sys.exit(e.returncode)\n"
        "except KeyboardInterrupt:\n"
        '    print("Script interrupted")\n'
        "    sys.exit(1)\n"
    )

    # Log the path setup on the meta-server side
    original_cwd = os.getcwd()
    logger.info(f"Meta-server starting from: {original_cwd}")
    logger.info(f"App directory added to path: {app_dir}")
    logger.info(f"Target script: {script_path}")

    wrapper_code = f"# Meta-server wrapper for script {script_name}\n" f"{bootstrap}"

    wrapper_script_path.write_text(wrapper_code, encoding="utf-8")
    return wrapper_script_path


def generate_meta_server_wrapper(
    func: Callable, app_dir: Optional[Path] = None
) -> Path:
    """
    Generate an ephemeral script that runs a server function with correct path resolution
    without changing the working directory. This preserves the original working directory
    for file operations while ensuring imports and script resolution work correctly.

    Args:
        func: The server function to wrap
        app_dir: The application directory (if None, will try to detect from function source)

    Returns:
        Path to the generated wrapper script
    """
    func_name = func.__name__
    module_name = getattr(func, "__module__", None)

    temp_dir = Path(tempfile.gettempdir()) / "terminaide_ephemeral"
    temp_dir.mkdir(exist_ok=True)
    script_path = temp_dir / f"meta_server_{func_name}.py"

    # Determine source directory if not provided
    if app_dir is None:
        try:
            source_file = inspect.getsourcefile(func) or inspect.getfile(func)
            if source_file:
                app_dir = Path(os.path.dirname(os.path.abspath(source_file)))
                logger.debug(f"Detected app_dir from function source: {app_dir}")
        except Exception as e:
            logger.warning(f"Could not determine app_dir from function: {e}")
            app_dir = Path(os.getcwd())  # fallback to current dir if all else fails

    # Handle if app_dir is provided as a string
    if isinstance(app_dir, str):
        app_dir = Path(app_dir)

    # Generate the path injection code - add both current working directory and app directory
    bootstrap = (
        "import sys, os\n"
        "from pathlib import Path\n"
        "# Preserve original working directory for file operations\n"
        "original_cwd = os.getcwd()\n"
        f'app_dir = r"{app_dir}"\n'
        "# Add paths to ensure imports work correctly\n"
        "if app_dir not in sys.path:\n"
        "    sys.path.insert(0, app_dir)\n"
        "if original_cwd not in sys.path:\n"
        "    sys.path.insert(0, original_cwd)\n"
        "# Monkey-patch sys.argv[0] to point to a file in the app directory\n"
        "# This ensures ScriptConfig validation resolves paths correctly\n"
        f'sys.argv[0] = str(Path(app_dir) / "main.py")\n\n'
    )

    # Log the path setup on the meta-server side
    original_cwd = os.getcwd()
    logger.info(f"Meta-server starting from: {original_cwd}")
    logger.info(f"App directory added to path: {app_dir}")

    # If it's a normal module (not main or mp_main)
    if module_name and module_name not in ("__main__", "__mp_main__"):
        wrapper_code = (
            f"# Meta-server wrapper for {func_name} from module {module_name}\n"
            f"{bootstrap}"
            f"# Import and run the server function (preserving working directory)\n"
            f"from {module_name} import {func_name}\n"
            f"{func_name}()\n"
        )
        script_path.write_text(wrapper_code, encoding="utf-8")
        return script_path

    # Inline fallback (if __main__ or dynamically defined)
    try:
        source_code = inspect.getsource(func)

        wrapper_code = (
            f"# Meta-server wrapper for {func_name} (from __main__ or dynamic)\n"
            f"{bootstrap}"
            f"# Define the server function\n"
            f"{source_code}\n\n"
            f"# Run the server function (preserving working directory)\n"
            f"{func_name}()\n"
        )
        script_path.write_text(wrapper_code, encoding="utf-8")
        return script_path
    except Exception as e:
        # Last resort: static error fallback
        error_script = (
            f'print("ERROR: cannot create meta-server wrapper for function {func_name}")\n'
            f'print("Module: {module_name}")\n'
            f'print("Error: {str(e)}")\n'
        )
        script_path.write_text(error_script, encoding="utf-8")
        return script_path


class ServeWithConfig:
    """Class responsible for handling the serving implementation for different modes."""

    @staticmethod
    def add_proxy_middleware_if_needed(app: FastAPI, config: TerminaideConfig) -> None:
        """
        Adds proxy header middleware if trust_proxy_headers=True in config.
        This ensures that X-Forwarded-Proto from proxies like ngrok is respected,
        preventing mixed-content errors behind HTTPS tunnels or load balancers.
        """
        if config.trust_proxy_headers:
            try:
                from .middleware import ProxyHeaderMiddleware

                # Make sure it isn't already added
                if not any(
                    m.cls.__name__ == "ProxyHeaderMiddleware"
                    for m in getattr(app, "user_middleware", [])
                ):
                    app.add_middleware(ProxyHeaderMiddleware)
                    logger.info("Added proxy header middleware for HTTPS detection")
            except Exception as e:
                logger.warning(f"Failed to add proxy header middleware: {e}")

    @classmethod
    def display_banner(cls, mode):
        """Display a minimal banner indicating the mode using Rich."""
        if os.environ.get("TERMINAIDE_BANNER_SHOWN") == "1":
            return
        os.environ["TERMINAIDE_BANNER_SHOWN"] = "1"

        try:
            from rich.console import Console
            from rich.panel import Panel

            mode_colors = {
                "function": "dark_orange",
                "script": "blue",
                "apps": "magenta",
                "meta": "bright_green",
            }
            color = mode_colors.get(mode, "yellow")
            mode_upper = mode.upper()

            console = Console(highlight=False)
            panel = Panel(
                f"TERMINAIDE {mode_upper} SERVER",
                border_style=color,
                expand=False,
                padding=(0, 1),
            )
            console.print(panel)
        except ImportError:
            mode_upper = mode.upper()
            banner = f"== TERMINAIDE SERVING IN {mode_upper} MODE =="
            print(f"\033[1m\033[92m{banner}\033[0m")

        logger.debug(f"Starting Terminaide in {mode_upper} mode")

    @classmethod
    def _wait_for_server(cls, url: str, timeout: int = 15) -> bool:
        """Wait for the server to be ready by checking health endpoint."""
        try:
            import requests
        except ImportError:
            logger.error(
                "requests library required for desktop mode. Install with: pip install requests"
            )
            return False

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Try health endpoint first
                try:
                    response = requests.get(f"{url}/health", timeout=2)
                    if response.status_code == 200:
                        logger.debug(f"Server ready at {url}")
                        return True
                except requests.exceptions.RequestException:
                    pass

                # Fallback: try root endpoint
                try:
                    response = requests.get(url, timeout=2)
                    if response.status_code == 200:
                        logger.debug(f"Server ready at {url} (via root endpoint)")
                        return True
                except requests.exceptions.RequestException:
                    pass

            except Exception:
                pass
            time.sleep(0.5)

        logger.error(f"Server at {url} did not become ready within {timeout} seconds")
        return False

    @classmethod
    def serve_desktop(cls, config: TerminaideConfig) -> None:
        """Serve the application in a desktop window using pywebview."""
        try:
            import webview
        except ImportError:
            logger.error(
                "pywebview library required for desktop mode. Install with: pip install pywebview"
            )
            print("\033[91mError: pywebview library required for desktop mode.\033[0m")
            print("Install with: pip install pywebview")
            return

        logger.info(f"Starting desktop application: {config.title}")

        # Create subprocess command to start the terminaide server
        server_args = [
            sys.executable,
            "-c",
            f"from terminaide import {config._mode}_serve; ",
        ]

        # Build the appropriate server command based on mode
        if config._mode == "function":
            # For functions, we need to create a wrapper script since we can't serialize the function
            func = config._target
            ephemeral_path = generate_function_wrapper(func)

            server_command = (
                f"from terminaide import serve_script; "
                f"serve_script(r'{ephemeral_path}', "
                f"port={config.port}, title='{config.title}', "
                f"debug={config.debug}, theme={config.theme}, "
                f"forward_env={repr(config.forward_env)})"
            )
        elif config._mode == "script":
            script_path = config._target
            server_command = (
                f"from terminaide import serve_script; "
                f"serve_script(r'{script_path}', "
                f"port={config.port}, title='{config.title}', "
                f"debug={config.debug}, theme={config.theme}, "
                f"forward_env={repr(config.forward_env)})"
            )
        elif config._mode == "meta":
            target = config._target
            app_dir = getattr(config, "_app_dir", None)

            if callable(target):
                # For meta functions, create wrapper
                ephemeral_path = generate_meta_server_wrapper(target, app_dir)
                server_command = (
                    f"from terminaide import serve_script; "
                    f"serve_script(r'{ephemeral_path}', "
                    f"port={config.port}, title='{config.title}', "
                    f"debug={config.debug}, theme={config.theme}, "
                    f"forward_env={repr(config.forward_env)})"
                )
            else:
                # For meta scripts
                script_path = Path(target)
                if not script_path.is_absolute():
                    script_path = Path.cwd() / script_path
                ephemeral_path = generate_meta_script_wrapper(script_path, app_dir)
                server_command = (
                    f"from terminaide import serve_script; "
                    f"serve_script(r'{ephemeral_path}', "
                    f"port={config.port}, title='{config.title}', "
                    f"debug={config.debug}, theme={config.theme}, "
                    f"forward_env={repr(config.forward_env)})"
                )
        elif config._mode == "apps":
            logger.error("Desktop mode for serve_apps is not yet implemented")
            print(
                "\033[91mError: Desktop mode for serve_apps is not yet implemented.\033[0m"
            )
            print(
                "Desktop mode currently supports serve_function, serve_script, and meta_serve only."
            )
            return
        else:
            logger.error(f"Unknown mode for desktop serving: {config._mode}")
            return

        # Update server args with the built command
        server_args[2] = server_command

        # Start the server subprocess
        logger.debug(f"Starting server subprocess for desktop mode")
        server_process = subprocess.Popen(
            server_args, cwd=Path.cwd(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        try:
            # Wait for server to be ready
            server_url = f"http://localhost:{config.port}"

            # Check if subprocess is still running before health check
            if server_process.poll() is not None:
                stdout, stderr = server_process.communicate()
                logger.error(
                    f"Server subprocess exited early with code: {server_process.returncode}"
                )
                if stderr:
                    logger.error(f"Server error: {stderr.decode()}")
                print("\033[91mError: Server failed to start\033[0m")
                return

            if not cls._wait_for_server(server_url, timeout=15):
                server_process.terminate()
                stdout, stderr = server_process.communicate(timeout=5)
                logger.error("Server failed to start")
                if stderr:
                    logger.error(f"Server stderr: {stderr.decode()}")
                print("\033[91mError: Server failed to start within timeout\033[0m")
                return

            logger.info(f"Server ready at {server_url}")

            # Create and show the desktop window
            logger.info(f"Opening desktop window: {config.title}")
            webview.create_window(
                title=config.title,
                url=server_url,
                width=config.desktop_width,
                height=config.desktop_height,
            )

            # This blocks until the window is closed
            webview.start()

            logger.info("Desktop window closed")

        except Exception as e:
            logger.error(f"Desktop application error: {e}")
            print(f"\033[91mDesktop application error: {e}\033[0m")
        finally:
            # Clean up: kill the server process when window closes
            logger.debug("Terminating server subprocess")
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Server process did not terminate gracefully, killing")
                server_process.kill()
                server_process.wait()

            logger.info("Desktop application cleanup complete")

    @classmethod
    def serve(cls, config) -> None:
        """Serves the application based on the configuration mode."""
        cls.display_banner(config._mode)

        # Check if desktop mode is requested
        if config.desktop:
            cls.serve_desktop(config)
            return

        if config._mode == "function":
            cls.serve_function(config)
        elif config._mode == "script":
            cls.serve_script(config)
        elif config._mode == "apps":
            cls.serve_apps(config)
        elif config._mode == "meta":
            cls.serve_meta(config)
        else:
            raise ValueError(f"Unknown serving mode: {config._mode}")

    @classmethod
    def serve_function(cls, config) -> None:
        """Implementation for serving a function."""
        if config.reload:
            # Reload mode - set environment variables and delegate to uvicorn
            func = config._target
            os.environ["TERMINAIDE_FUNC_NAME"] = func.__name__
            os.environ["TERMINAIDE_FUNC_MOD"] = (
                func.__module__ if func.__module__ else ""
            )
            os.environ["TERMINAIDE_PORT"] = str(config.port)
            os.environ["TERMINAIDE_TITLE"] = config.title
            os.environ["TERMINAIDE_DEBUG"] = "1" if config.debug else "0"
            os.environ["TERMINAIDE_THEME"] = str(config.theme or {})
            os.environ["TERMINAIDE_FORWARD_ENV"] = str(config.forward_env)

            if hasattr(config, "preview_image") and config.preview_image:
                os.environ["TERMINAIDE_PREVIEW_IMAGE"] = str(config.preview_image)

            uvicorn.run(
                "terminaide.termin_api:function_app_factory",
                factory=True,
                host="0.0.0.0",
                port=config.port,
                reload=True,
                log_level="info" if config.debug else "warning",
            )
        else:
            # Direct mode - use local generate_function_wrapper
            func = config._target
            ephemeral_path = generate_function_wrapper(func)

            script_config = type(config)(
                port=config.port,
                title=config.title,
                theme=config.theme,
                debug=config.debug,
                forward_env=config.forward_env,
                ttyd_options=config.ttyd_options,
                template_override=config.template_override,
                trust_proxy_headers=config.trust_proxy_headers,
                mount_path=config.mount_path,
                ttyd_port=config.ttyd_port,
            )
            if hasattr(config, "preview_image"):
                script_config.preview_image = config.preview_image

            script_config._target = ephemeral_path
            script_config._mode = "function"
            script_config._original_function_name = func.__name__

            logger.debug(
                f"Using title: {script_config.title} for function {func.__name__}"
            )

            cls.serve_script(script_config)

    @classmethod
    def serve_meta(cls, config) -> None:
        """Implementation for serving a meta-server (a server that serves terminal instances)."""
        target = config._target
        app_dir = getattr(config, "_app_dir", None)

        if callable(target):
            # Handle function target
            logger.info(f"Creating meta-server wrapper for function: {target.__name__}")
            ephemeral_path = generate_meta_server_wrapper(target, app_dir)
        else:
            # Handle script target
            script_path = Path(target)
            if not script_path.is_absolute():
                script_path = Path.cwd() / script_path

            if not script_path.exists():
                logger.error(f"Meta-server script not found: {script_path}")
                print(
                    f"\033[91mError: Meta-server script not found: {script_path}\033[0m"
                )
                return

            logger.info(f"Creating meta-server wrapper for script: {script_path}")
            ephemeral_path = generate_meta_script_wrapper(script_path, app_dir)

        # Create a new config for the script serving
        script_config = type(config)(
            port=config.port,
            title=config.title,
            theme=config.theme,
            debug=config.debug,
            desktop=config.desktop,
            desktop_width=config.desktop_width,
            desktop_height=config.desktop_height,
            forward_env=config.forward_env,
            ttyd_options=config.ttyd_options,
            template_override=config.template_override,
            trust_proxy_headers=config.trust_proxy_headers,
            mount_path=config.mount_path,
            ttyd_port=config.ttyd_port,
        )

        # Copy preview_image if available
        if hasattr(config, "preview_image"):
            script_config.preview_image = config.preview_image

        # Set the target to the wrapper script
        script_config._target = ephemeral_path
        script_config._mode = "meta"  # Preserve the meta mode

        if callable(target):
            script_config._original_function_name = target.__name__
        else:
            script_config._original_script_name = script_path.name

        logger.info("Meta-server wrapper script created at:")
        logger.info(f"{ephemeral_path}")
        logger.debug(f"Using title: {script_config.title} for meta-server")

        # Leverage the existing script serving functionality
        cls.serve_script(script_config)

    @classmethod
    def serve_script(cls, config) -> None:
        """Implementation for serving a script."""
        script_path = config._target
        if not isinstance(script_path, Path):
            script_path = Path(script_path)

        script_path = smart_resolve_path(script_path)
        if not script_path.exists():
            print(f"\033[91mError: Script not found: {script_path}\033[0m")
            return

        if config.reload:
            os.environ["TERMINAIDE_SCRIPT_PATH"] = str(script_path)
            os.environ["TERMINAIDE_PORT"] = str(config.port)
            os.environ["TERMINAIDE_TITLE"] = config.title
            os.environ["TERMINAIDE_DEBUG"] = "1" if config.debug else "0"
            os.environ["TERMINAIDE_THEME"] = str(config.theme or {})
            os.environ["TERMINAIDE_FORWARD_ENV"] = str(config.forward_env)
            os.environ["TERMINAIDE_MODE"] = config._mode
            if hasattr(config, "preview_image") and config.preview_image:
                os.environ["TERMINAIDE_PREVIEW_IMAGE"] = str(config.preview_image)

            uvicorn.run(
                "terminaide.termin_api:script_app_factory",
                factory=True,
                host="0.0.0.0",
                port=config.port,
                reload=True,
                log_level="info" if config.debug else "warning",
            )
        else:
            # Direct mode
            app = FastAPI(title=f"Terminaide - {config.title}")
            # <-- ADD PROXY MIDDLEWARE FOR SOLO MODES -->
            cls.add_proxy_middleware_if_needed(app, config)

            ttyd_config = convert_terminaide_config_to_ttyd_config(config, script_path)

            original_lifespan = app.router.lifespan_context

            @asynccontextmanager
            async def terminaide_merged_lifespan(_app: FastAPI):
                if original_lifespan is not None:
                    async with original_lifespan(_app):
                        async with terminaide_lifespan(_app, ttyd_config):
                            yield
                else:
                    async with terminaide_lifespan(_app, ttyd_config):
                        yield

            app.router.lifespan_context = terminaide_merged_lifespan

            def handle_exit(sig, frame):
                print("\033[93mShutting down...\033[0m")
                sys.exit(0)

            signal.signal(signal.SIGINT, handle_exit)
            signal.signal(signal.SIGTERM, handle_exit)

            uvicorn.run(
                app,
                host="0.0.0.0",
                port=config.port,
                log_level="info" if config.debug else "warning",
            )

    @classmethod
    def serve_apps(cls, config) -> None:
        """Implementation for serving multiple apps."""
        app = config._app
        terminal_routes = config._target

        # Process function-based routes to generate ephemeral script wrappers
        ttyd_config = convert_terminaide_config_to_ttyd_config(config)

        # Generate wrapper scripts for all function-based routes
        for script_config in ttyd_config.script_configs:
            if script_config.is_function_based:
                func = script_config.function_object
                if func is not None:
                    logger.debug(
                        f"Generating wrapper script for function '{func.__name__}' at route {script_config.route_path}"
                    )
                    wrapper_path = generate_function_wrapper(func)
                    script_config.set_function_wrapper_path(wrapper_path)
                    logger.debug(
                        f"Function '{func.__name__}' will use wrapper script at {wrapper_path}"
                    )

        if config.trust_proxy_headers:
            try:
                from .middleware import ProxyHeaderMiddleware

                if not any(
                    m.cls.__name__ == "ProxyHeaderMiddleware"
                    for m in getattr(app, "user_middleware", [])
                ):
                    app.add_middleware(ProxyHeaderMiddleware)
                    logger.info("Added proxy header middleware for HTTPS detection")
            except Exception as e:
                logger.warning(f"Failed to add proxy header middleware: {e}")

        sentinel_attr = "_terminaide_lifespan_attached"
        if getattr(app.state, sentinel_attr, False):
            return

        setattr(app.state, sentinel_attr, True)

        original_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def terminaide_merged_lifespan(_app: FastAPI):
            if original_lifespan is not None:
                async with original_lifespan(_app):
                    async with terminaide_lifespan(_app, ttyd_config):
                        yield
            else:
                async with terminaide_lifespan(_app, ttyd_config):
                    yield

        app.router.lifespan_context = terminaide_merged_lifespan


class AppFactory:
    """Factory class for creating FastAPI applications based on environment variables."""

    @classmethod
    def function_app_factory(cls) -> FastAPI:
        """
        Called by uvicorn with factory=True in function mode when reload=True.
        We'll try to re-import the function from its module if it's not __main__/__mp_main__.
        If it *is* in main or mp_main, we search sys.modules for the function, then inline.
        """
        func_name = os.environ.get("TERMINAIDE_FUNC_NAME", "")
        func_mod = os.environ.get("TERMINAIDE_FUNC_MOD", "")
        port_str = os.environ["TERMINAIDE_PORT"]
        title = os.environ["TERMINAIDE_TITLE"]
        debug = os.environ.get("TERMINAIDE_DEBUG") == "1"
        theme_str = os.environ.get("TERMINAIDE_THEME") or "{}"
        forward_env_str = os.environ.get("TERMINAIDE_FORWARD_ENV", "True")
        preview_image_str = os.environ.get("TERMINAIDE_PREVIEW_IMAGE")

        func = None
        if func_mod and func_mod not in ("__main__", "__mp_main__"):
            try:
                mod = __import__(func_mod, fromlist=[func_name])
                func = getattr(mod, func_name, None)
            except:
                logger.warning(f"Failed to import {func_name} from {func_mod}")

        if func is None and func_mod in ("__main__", "__mp_main__"):
            candidate_mod = sys.modules.get(func_mod)
            if candidate_mod and hasattr(candidate_mod, func_name):
                func = getattr(candidate_mod, func_name)

        ephemeral_path = None
        if func is not None and callable(func):
            ephemeral_path = generate_function_wrapper(func)
        else:
            temp_dir = Path(tempfile.gettempdir()) / "terminaide_ephemeral"
            temp_dir.mkdir(exist_ok=True)
            ephemeral_path = temp_dir / f"{func_name}_cannot_reload.py"
            ephemeral_path.write_text(
                f'print("ERROR: cannot reload function {func_name} from module={func_mod}")\n',
                encoding="utf-8",
            )

        import ast

        theme = {}
        try:
            theme = ast.literal_eval(theme_str)
        except:
            pass

        forward_env = True
        try:
            forward_env = ast.literal_eval(forward_env_str)
        except:
            pass

        app = FastAPI(title=f"Terminaide - {title}")

        # Build config so we can add proxy middleware, etc.
        config = TerminaideConfig(
            port=int(port_str),
            title=title,
            theme=theme,
            debug=debug,
            forward_env=forward_env,
        )

        if preview_image_str:
            preview_path = Path(preview_image_str)
            if preview_path.exists():
                config.preview_image = preview_path
            else:
                logger.warning(f"Preview image not found: {preview_image_str}")

        config._target = ephemeral_path
        config._mode = "function"

        ServeWithConfig.display_banner(config._mode)

        # <-- ADD PROXY MIDDLEWARE FOR RELOAD MODE -->
        ServeWithConfig.add_proxy_middleware_if_needed(app, config)

        ttyd_config = convert_terminaide_config_to_ttyd_config(config, ephemeral_path)

        original_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def merged_lifespan(_app: FastAPI):
            if original_lifespan is not None:
                async with original_lifespan(_app):
                    async with terminaide_lifespan(_app, ttyd_config):
                        yield
            else:
                async with terminaide_lifespan(_app, ttyd_config):
                    yield

        app.router.lifespan_context = merged_lifespan

        return app

    @classmethod
    def script_app_factory(cls) -> FastAPI:
        """
        Called by uvicorn with factory=True in script mode when reload=True.
        Rebuilds the FastAPI app from environment variables.
        """
        script_path_str = os.environ["TERMINAIDE_SCRIPT_PATH"]
        port_str = os.environ["TERMINAIDE_PORT"]
        title = os.environ["TERMINAIDE_TITLE"]
        debug = os.environ.get("TERMINAIDE_DEBUG") == "1"
        theme_str = os.environ.get("TERMINAIDE_THEME") or "{}"
        forward_env_str = os.environ.get("TERMINAIDE_FORWARD_ENV", "True")
        mode = os.environ.get("TERMINAIDE_MODE", "script")
        preview_image_str = os.environ.get("TERMINAIDE_PREVIEW_IMAGE")

        import ast

        theme = {}
        try:
            theme = ast.literal_eval(theme_str)
        except:
            pass

        forward_env = True
        try:
            forward_env = ast.literal_eval(forward_env_str)
        except:
            pass

        script_path = Path(script_path_str)
        app = FastAPI(title=f"Terminaide - {title}")

        config = TerminaideConfig(
            port=int(port_str),
            title=title,
            theme=theme,
            debug=debug,
            forward_env=forward_env,
        )

        if preview_image_str:
            preview_path = Path(preview_image_str)
            if preview_path.exists():
                config.preview_image = preview_path
            else:
                logger.warning(f"Preview image not found: {preview_image_str}")

        config._target = script_path
        config._mode = mode

        ServeWithConfig.display_banner(config._mode)

        # <-- ADD PROXY MIDDLEWARE FOR RELOAD MODE -->
        ServeWithConfig.add_proxy_middleware_if_needed(app, config)

        ttyd_config = convert_terminaide_config_to_ttyd_config(config, script_path)

        original_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def merged_lifespan(_app: FastAPI):
            if original_lifespan is not None:
                async with original_lifespan(_app):
                    async with terminaide_lifespan(_app, ttyd_config):
                        yield
            else:
                async with terminaide_lifespan(_app, ttyd_config):
                    yield

        app.router.lifespan_context = merged_lifespan

        return app
