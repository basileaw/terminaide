# utilities/release.py

"""
Release script for terminaide.
Usage:
python release.py patch    # Release patch version
python release.py minor    # Release minor version
python release.py major    # Release major version
"""
import os
import sys
import argparse
import subprocess
from getpass import getpass
from subprocess import CalledProcessError
from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme

# Initialize rich console with custom theme
theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red bold",
    "success": "green bold"
})
console = Console(theme=theme)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("type", choices=["patch", "minor", "major"],
                       help="Version type to release")
    return parser.parse_args()

def run_command(cmd, description, exit_on_error=True, env=None):
    """Run a command with proper error handling."""
    console.print(f"[info]► Executing:[/] {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            env=env
        )
        if result.stdout.strip():
            console.print(Panel(result.stdout.strip(), border_style="cyan"))
        return result
    except CalledProcessError as e:
        console.print(Panel(f"[error]Error during {description}[/]", border_style="red"))
        console.print(f"[error]Command:[/] {' '.join(cmd)}")
        console.print(f"[error]Exit code:[/] {e.returncode}")
        
        if e.stdout:
            console.print("[error]Standard output:[/]")
            console.print(Panel(e.stdout, border_style="red"))
        if e.stderr:
            console.print("[error]Standard error:[/]")
            console.print(Panel(e.stderr, border_style="red"))
        
        if exit_on_error:
            console.print(f"\n[error]Aborting release process due to error in {description}[/]")
            sys.exit(e.returncode)
        else:
            console.print(f"\n[warning]Continuing despite error in {description}[/]")
            return None

def main():
    args = parse_args()
    
    console.rule("[bold cyan]Starting Release Process[/]")
    
    # Update version
    run_command(["poetry", "version", args.type], "version update")
    
    # Get new version
    version_result = run_command(
        ["poetry", "version", "-s"],
        "version retrieval"
    )
    version = version_result.stdout.strip()
    console.print(f"\n[info]New version:[/] [bold cyan]{version}[/]\n")
    
    # Git commands
    console.rule("[bold cyan]Git Operations[/]")
    run_command(["git", "add", "pyproject.toml"], "git add")
    run_command(["git", "commit", "-m", f"release {version}"], "git commit")
    run_command(["git", "tag", f"v{version}"], "git tag")
    
    # Try to push, but continue even if it fails
    push_result = run_command(["git", "push"], "git push", exit_on_error=False)
    tags_result = run_command(["git", "push", "--tags"], "git push tags", exit_on_error=False)
    
    if not push_result or not tags_result:
        console.print(Panel.fit(
            "[warning]Git push operations failed. You may need to manually push commits and tags.\n"
            "You can do this with:\n"
            "  git push\n"
            "  git push --tags[/]",
            border_style="yellow"
        ))
        proceed = console.input("\nDo you want to continue with package publishing anyway? (y/n): ")
        if proceed.lower() != 'y':
            console.print("[warning]Aborting release process.[/]")
            return
    
    # Get PyPI token and publish
    console.rule("[bold cyan]PyPI Publishing[/]")
    console.print("\n[info]Please enter your PyPI token (input will be hidden):[/]")
    token = getpass()
    env = os.environ.copy()
    env["POETRY_PYPI_TOKEN_PYPI"] = token
    
    try:
        run_command(
            ["poetry", "publish", "--build"],
            "poetry publish",
            exit_on_error=True,
            env=env
        )
        console.print(Panel(
            f"[success]Successfully released version {version}![/]",
            border_style="green"
        ))
    except Exception as e:
        console.print(f"[error]Error during package publishing:[/] {str(e)}")
    finally:
        # Clean up token from environment
        if "POETRY_PYPI_TOKEN_PYPI" in os.environ:
            del os.environ["POETRY_PYPI_TOKEN_PYPI"]

if __name__ == "__main__":
    main()