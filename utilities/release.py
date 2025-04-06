#!/usr/bin/env python3

import argparse
import subprocess
import sys
import time
import requests
import os
from pathlib import Path

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

def run(cmd, check=True):
    result = subprocess.run(cmd, text=True, capture_output=True)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            returncode=result.returncode,
            cmd=cmd,
            output=result.stdout,
            stderr=result.stderr
        )
    return result.stdout.strip()

def wait_for_pypi(package_name, expected_version, max_retries=12, interval=5):
    sys.stdout.write(f"Polling PyPI for version {expected_version} of '{package_name}'")
    sys.stdout.flush()
    for _ in range(max_retries):
        try:
            response = requests.get(f"https://pypi.org/pypi/{package_name}/json", timeout=10)
            if response.status_code == 200:
                data = response.json()
                latest_version = data["info"]["version"]
                if latest_version == expected_version:
                    sys.stdout.write(f"\n{GREEN} {expected_version} published!{RESET}\n")
                    sys.stdout.flush()
                    return
        except requests.exceptions.RequestException:
            pass
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(interval)
    sys.stdout.write(f"\n{RED}Timed out waiting for {expected_version} on PyPI.{RESET}\n")
    sys.stdout.flush()

def confirm_proceed(package_name, current_version, new_version, dry_run):
    print(f"--- Release Confirmation ---")
    print(f"Package name: {package_name}")
    print(f"Current version: {current_version}")
    print(f"New version: {new_version}")
    print(f"Dry run: {'Yes' if dry_run else 'No'}")
    print(f"Actions to be performed:")
    print(f" - Bump version in pyproject.toml")
    print(f" - Commit version bump")
    print(f" - Create git tag")
    print(f" - Push commit and tag to origin")
    if not dry_run:
        print(f" - Trigger GitHub Action to publish to PyPI")
        print(f" - Poll PyPI to confirm publication")
    else:
        print(f" - (Dry run mode, no changes will be made)")
    print(f"----------------------------")
    response = input("Proceed? (Y/n): ").strip().lower()
    if response not in ("", "y", "yes"):
        print(f"{RED}Aborted by user.{RESET}")
        sys.exit(0)

def check_publish_workflow_exists(workflow_path=None):
    if workflow_path is None:
        workflow_path = ".github/workflows/publish.yml"
    workflow_file = Path(workflow_path)
    if not workflow_file.is_file():
        print(f"{RED}Error: publish workflow not found at {workflow_path}.{RESET}")
        print(f"{RED}Ensure your GitHub Action is set up before releasing.{RESET}")
        sys.exit(1)

def get_package_name():
    try:
        # Try to extract package name from pyproject.toml
        if Path("pyproject.toml").exists():
            content = Path("pyproject.toml").read_text()
            # Look for name = "package_name" in pyproject.toml
            for line in content.split("\n"):
                if line.strip().startswith("name = "):
                    # Extract the package name from quotes
                    name = line.split("=")[1].strip()
                    name = name.strip('"').strip("'")
                    return name
    except Exception as e:
        print(f"{RED}Error extracting package name from pyproject.toml: {e}{RESET}")
        
    # If automatic detection fails, prompt the user
    return input("Enter the package name: ").strip()

def main():
    parser = argparse.ArgumentParser(description="Bump version, commit, tag, push, and poll PyPI.")
    parser.add_argument("type", choices=["patch", "minor", "major"], help="Version bump type.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without making changes.")
    parser.add_argument("--package-name", help="Override the package name (auto-detected from pyproject.toml by default).")
    parser.add_argument("--workflow-path", help="Path to the GitHub publish workflow (default: .github/workflows/publish.yml).")
    parser.add_argument("--skip-pypi-check", action="store_true", help="Skip checking PyPI for the new version.")
    args = parser.parse_args()

    dry_run = args.dry_run
    package_name = args.package_name or get_package_name()

    # Check publish workflow exists
    check_publish_workflow_exists(args.workflow_path)

    # Check clean git state
    status = run(["git", "status", "--porcelain"], check=False)
    if status:
        print(f"{RED}Error: Repository has uncommitted changes. Commit or stash them first.{RESET}")
        sys.exit(1)

    old_commit = run(["git", "rev-parse", "HEAD"])
    current_version = run(["poetry", "version", "-s"])

    if dry_run:
        new_version = "<new-version>"
    else:
        version_output = run(["poetry", "version", args.type, "--dry-run"])
        new_version = version_output.split()[-1]

    confirm_proceed(package_name, current_version, new_version, dry_run)

    version_cmd = ["poetry", "version", args.type]
    commit_message = f"release {new_version}"
    tag_name = f"v{new_version}"

    try:
        if dry_run:
            print(f"[DRY-RUN] Would run: {' '.join(version_cmd)}")
            print(f"[DRY-RUN] Would git add pyproject.toml")
            print(f"[DRY-RUN] Would commit with message: '{commit_message}'")
            print(f"[DRY-RUN] Would create git tag: '{tag_name}'")
            print(f"[DRY-RUN] Would push commit and tag to origin")
        else:
            run(version_cmd)
            new_version = run(["poetry", "version", "-s"])
            run(["git", "add", "pyproject.toml"])
            run(["git", "commit", "-m", commit_message])
            run(["git", "tag", tag_name])
            print(f"Pushing commit and tag '{tag_name}' to origin...")
            run(["git", "push", "origin", "HEAD"])
            run(["git", "push", "origin", tag_name])
            if not args.skip_pypi_check:
                wait_for_pypi(package_name, new_version)

        print(f"{GREEN}Done! Version {new_version}{' (dry run)' if dry_run else ''}.{RESET}")

    except subprocess.CalledProcessError as e:
        print(f"{RED}Error occurred during release process.{RESET}")
        print(f"Command: {' '.join(e.cmd)}")
        if e.output:
            print(f"Output:\n{e.output}")
        if e.stderr:
            print(f"Error:\n{e.stderr}")
        if not dry_run:
            print("Rolling back changes...")
            run(["git", "checkout", "pyproject.toml"], check=False)
            run(["git", "reset", "--hard", old_commit], check=False)
            run(["git", "tag", "-d", tag_name], check=False)
        sys.exit(1)

if __name__ == "__main__":
    main()