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


def make_github_graphql_request(query, variables=None, token=None):
    """Make a GitHub GraphQL API request."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    data = {
        "query": query,
        "variables": variables or {}
    }
    
    try:
        response = requests.post(
            "https://api.github.com/graphql",
            headers=headers,
            json=data,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        
        if "errors" in result:
            for error in result["errors"]:
                console.print(f"[red]GraphQL error: {error['message']}[/red]")
            sys.exit(1)
            
        return result["data"]
        
    except requests.exceptions.RequestException as e:
        console.print(f"[red]GitHub GraphQL request failed: {e}[/red]")
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

    # Format issue type with label color (preserve original casing)
    if label_color:
        r = int(label_color[0:2], 16)
        g = int(label_color[2:4], 16) 
        b = int(label_color[4:6], 16)
        formatted_issue_type = f"\033[38;2;{r};{g};{b}m{label}\033[0m"
    else:
        formatted_issue_type = label
    
    print(f"\033[32m✓\033[0m Created {formatted_issue_type} \033[32m{issue['number']}\033[0m → \033[90m{issue['html_url']}\033[0m")


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
            f"[green]{issue['number']}[/green]",
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
                
                # Get label information
                label_name = issue["labels"][0]["name"] if issue["labels"] else "issue"
                label_color = get_label_color(repo, label_name, token) if issue["labels"] else None
                
                # Format label with ANSI color
                if label_color:
                    r = int(label_color[0:2], 16)
                    g = int(label_color[2:4], 16)
                    b = int(label_color[4:6], 16)
                    formatted_label = f"\033[38;2;{r};{g};{b}m{label_name}\033[0m"
                else:
                    formatted_label = label_name
                
                print(f"\033[32m✓\033[0m Resolved {formatted_label} \033[32m{issue_num}\033[0m → \033[90m{issue['html_url']}\033[0m")

            elif operation == "delete":
                # Use GraphQL API to actually delete the issue
                query = """
                mutation DeleteIssue($issueId: ID!) {
                    deleteIssue(input: {issueId: $issueId}) {
                        repository {
                            id
                        }
                    }
                }
                """
                
                # First get the issue's GraphQL ID
                id_query = """
                query GetIssueId($owner: String!, $name: String!, $number: Int!) {
                    repository(owner: $owner, name: $name) {
                        issue(number: $number) {
                            id
                        }
                    }
                }
                """
                
                repo_parts = repo.split("/")
                id_variables = {
                    "owner": repo_parts[0],
                    "name": repo_parts[1], 
                    "number": int(issue_num)
                }
                
                id_result = make_github_graphql_request(id_query, id_variables, token)
                issue_id = id_result["repository"]["issue"]["id"]
                
                # Now delete the issue
                variables = {"issueId": issue_id}
                make_github_graphql_request(query, variables, token)
                
                # Get label information for display
                label_name = issue["labels"][0]["name"] if issue["labels"] else "issue"
                label_color = get_label_color(repo, label_name, token) if issue["labels"] else None
                
                # Format label with ANSI color
                if label_color:
                    r = int(label_color[0:2], 16)
                    g = int(label_color[2:4], 16)
                    b = int(label_color[4:6], 16)
                    formatted_label = f"\033[38;2;{r};{g};{b}m{label_name}\033[0m"
                else:
                    formatted_label = label_name
                
                print(f"\033[32m✓\033[0m Deleted {formatted_label} \033[32m{issue_num}\033[0m: \033[1m{issue['title']}\033[0m")

        except Exception as e:
            print(f"\033[31m✗\033[0m Issue \033[32m{issue_num}\033[0m not found or error occurred")


def main():
    """Main entry point for the issues utility."""
    parser = argparse.ArgumentParser(description="GitHub issue management utility")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a new issue")
    create_parser.add_argument(
        "label", choices=["bug", "task", "idea"], help="Issue label/type"
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
        # Prompt for title interactively
        title = console.input("[bright_blue]?[/bright_blue] Title: ").strip()
        if not title:
            console.print("[red]Error:[/red] Title cannot be empty")
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
