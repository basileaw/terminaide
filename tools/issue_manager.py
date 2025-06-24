# issue_manager.py

import os
import sys
import argparse
import requests
import subprocess
from pathlib import Path
from rich.console import Console
from rich.table import Table
from datetime import datetime

console = Console()


def load_env():
    """Load environment variables from .env file if it exists."""
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key] = value


def get_repo_info():
    """Get repository information from git remote."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        url = result.stdout.strip()

        # Convert various URL formats to owner/repo
        if url.startswith("git@github.com:"):
            repo = url.replace("git@github.com:", "").replace(".git", "")
        elif url.startswith("https://github.com/"):
            repo = url.replace("https://github.com/", "").replace(".git", "")
        else:
            raise ValueError(f"Unsupported git remote URL format: {url}")

        return repo
    except subprocess.CalledProcessError:
        console.print(
            "[red]Error: Not a git repository or no remote origin found[/red]"
        )
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error getting repository info: {e}[/red]")
        sys.exit(1)


def get_github_token():
    """Get GitHub token from environment variables."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        console.print("[red]Error: GITHUB_TOKEN environment variable not set[/red]")
        console.print("Please set your GitHub token in .env file or environment")
        sys.exit(1)
    return token


def make_github_request(method, url, data=None, token=None):
    """Make a GitHub API request with proper error handling."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }

    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=10)
        elif method.upper() == "PATCH":
            response = requests.patch(url, headers=headers, json=data, timeout=10)
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=headers, timeout=10)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        response.raise_for_status()
        return response.json() if response.content else {}

    except requests.exceptions.RequestException as e:
        console.print(f"[red]GitHub API request failed: {e}[/red]")
        if hasattr(e, "response") and e.response is not None:
            try:
                error_data = e.response.json()
                if "message" in error_data:
                    console.print(
                        f"[red]GitHub API error: {error_data['message']}[/red]"
                    )
            except:
                pass
        sys.exit(1)


def get_label_color(repo, label_name, token):
    """Get the color for a specific label."""
    url = f"https://api.github.com/repos/{repo}/labels"
    labels = make_github_request("GET", url, token=token)

    for label in labels:
        if label["name"] == label_name:
            return label["color"]
    return None


def create_issue(repo, title, label, token):
    """Create a new GitHub issue."""
    url = f"https://api.github.com/repos/{repo}/issues"
    data = {"title": title, "body": "", "labels": [label]}

    issue = make_github_request("POST", url, data=data, token=token)

    # Get label color for display
    label_color = get_label_color(repo, label, token)
    color_code = ""
    if label_color:
        # Convert hex color to RGB values for terminal display
        r = int(label_color[0:2], 16)
        g = int(label_color[2:4], 16)
        b = int(label_color[4:6], 16)
        color_code = f"rgb({r},{g},{b})"

    # Format the output to match the original Makefile style
    issue_type = label.capitalize()
    console.print(
        f"[green]✓[/green] Created [{color_code}]{issue_type}[/{color_code}] [green]#{issue['number']}[/green]: [bold]\"{title}\"[/bold]"
    )
    console.print(f"[dim]→ {issue['html_url']}[/dim]")


def list_issues(repo, token):
    """List all open GitHub issues."""
    # Get issues
    issues_url = f"https://api.github.com/repos/{repo}/issues?state=open"
    issues = make_github_request("GET", issues_url, token=token)

    if not issues:
        console.print("[dim]No open issues found[/dim]")
        return

    # Get labels for color mapping
    labels_url = f"https://api.github.com/repos/{repo}/labels"
    labels = make_github_request("GET", labels_url, token=token)
    label_colors = {label["name"]: label["color"] for label in labels}

    # Create table
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", width=6)
    table.add_column("TITLE", width=50)
    table.add_column("LABEL", width=10)
    table.add_column("AUTHOR", width=12)
    table.add_column("CREATED", width=10)

    for issue in issues:
        # Format date
        created_date = datetime.fromisoformat(
            issue["created_at"].replace("Z", "+00:00")
        )
        short_date = created_date.strftime("%Y-%m-%d")

        # Get label and color
        label_name = issue["labels"][0]["name"] if issue["labels"] else ""
        label_color = label_colors.get(label_name, "")

        # Format label with color
        if label_name and label_color:
            r = int(label_color[0:2], 16)
            g = int(label_color[2:4], 16)
            b = int(label_color[4:6], 16)
            formatted_label = f"[rgb({r},{g},{b})]{label_name}[/rgb({r},{g},{b})]"
        else:
            formatted_label = f"[dim]{label_name}[/dim]" if label_name else ""

        table.add_row(
            f"[green]#{issue['number']}[/green]",
            issue["title"][:50],
            formatted_label,
            issue["user"]["login"],
            short_date,
        )

    console.print(table)


def batch_operation(repo, issue_numbers, operation, token):
    """Perform batch operations on issues (resolve or delete)."""
    operation_names = {"resolve": "Resolved", "delete": "Deleted"}
    operation_name = operation_names.get(operation, operation.capitalize())

    for issue_num in issue_numbers:
        try:
            # Get issue info first
            issue_url = f"https://api.github.com/repos/{repo}/issues/{issue_num}"
            issue = make_github_request("GET", issue_url, token=token)

            if operation == "resolve":
                # Close the issue
                data = {"state": "closed"}
                make_github_request("PATCH", issue_url, data=data, token=token)
                console.print(
                    f"[green]✓[/green] Resolved issue [green]#{issue_num}[/green]: [bold]\"{issue['title']}\"[/bold]"
                )
                console.print(f"[dim]→ {issue['html_url']}[/dim]")

            elif operation == "delete":
                # Note: GitHub API doesn't allow deleting issues, only closing them
                # We'll close them instead and note this limitation
                data = {"state": "closed"}
                make_github_request("PATCH", issue_url, data=data, token=token)
                console.print(
                    f"[red]✔[/red] Closed issue [green]#{issue_num}[/green]: [bold]\"{issue['title']}\"[/bold]"
                )
                console.print(
                    "[dim]Note: GitHub API doesn't support deleting issues, so it was closed instead[/dim]"
                )

        except Exception as e:
            console.print(
                f"[red]✗[/red] Issue [green]#{issue_num}[/green] not found or error occurred"
            )


def main():
    """Main entry point for the issues utility."""
    parser = argparse.ArgumentParser(description="GitHub issue management utility")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new issue")
    create_parser.add_argument(
        "label", choices=["bug", "task", "idea"], help="Issue label/type"
    )
    create_parser.add_argument(
        "title", nargs="*", help="Issue title (multiple words allowed)"
    )

    # List command
    subparsers.add_parser("list", help="List all open issues")

    # Resolve command
    resolve_parser = subparsers.add_parser("resolve", help="Resolve (close) issues")
    resolve_parser.add_argument(
        "issues", nargs="*", type=int, help="Issue numbers to resolve"
    )

    # Delete command (actually closes)
    delete_parser = subparsers.add_parser("delete", help="Delete (close) issues")
    delete_parser.add_argument(
        "issues", nargs="*", type=int, help="Issue numbers to delete"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load environment variables
    load_env()

    # Get repository and token
    repo = get_repo_info()
    token = get_github_token()

    # Execute command
    if args.command == "create":
        title = " ".join(args.title) if args.title else ""
        if not title:
            console.print(
                f'[red]Error:[/red] Please provide a title: make {args.label} "Your issue title"'
            )
            sys.exit(1)
        create_issue(repo, title, args.label, token)
    elif args.command == "list":
        list_issues(repo, token)
    elif args.command == "resolve":
        if not args.issues:
            console.print(
                "[red]Error:[/red] Please provide issue numbers: make resolve 1 2 3"
            )
            sys.exit(1)
        batch_operation(repo, args.issues, "resolve", token)
    elif args.command == "delete":
        if not args.issues:
            console.print(
                "[red]Error:[/red] Please provide issue numbers: make delete 1 2 3"
            )
            sys.exit(1)
        batch_operation(repo, args.issues, "delete", token)


if __name__ == "__main__":
    main()
