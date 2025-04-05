#!/usr/bin/env python3

import argparse
import subprocess
import sys
import time
import requests

def run(cmd, check=True):
    """
    Run a shell command and return stdout. Raise CalledProcessError if fails.
    """
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
    """
    Poll PyPI for up to (max_retries) times, waiting (interval) seconds
    between polls. If version is found, return. Otherwise, warn after timeout.
    """
    print(f"Polling PyPI for version {expected_version} of '{package_name}'...")

    for attempt in range(max_retries):
        print(f"Attempt {attempt+1}/{max_retries}...")
        try:
            response = requests.get(f"https://pypi.org/pypi/{package_name}/json", timeout=10)
            if response.status_code == 200:
                data = response.json()
                latest_version = data["info"]["version"]
                if latest_version == expected_version:
                    print(f"PyPI has version {expected_version}. Publication confirmed.")
                    return
                else:
                    print(f"Current PyPI version is {latest_version}. Waiting for {expected_version}...")
            else:
                print(f"PyPI responded with status {response.status_code}. Retrying...")
        except requests.exceptions.RequestException as e:
            print(f"Request to PyPI failed ({e}). Retrying...")

        time.sleep(interval)

    print(f"Timed out waiting for {expected_version} on PyPI after {max_retries*interval} seconds.")
    print("It might still be processing. Check again later if needed.")

def main():
    parser = argparse.ArgumentParser(description="Bump version, commit, tag, push, and poll PyPI.")
    parser.add_argument("type", choices=["patch", "minor", "major"], help="Version bump type.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without making changes.")
    args = parser.parse_args()

    dry_run = args.dry_run
    package_name = "terminaide"  # Update if your package name changes

    # Step 1: Check for clean git state
    status = run(["git", "status", "--porcelain"], check=False)
    if status:
        print("Error: Repository has uncommitted changes. Commit or stash them first.")
        sys.exit(1)

    # Record current commit for potential rollback
    old_commit = run(["git", "rev-parse", "HEAD"])
    old_version = run(["poetry", "version", "-s"])  # e.g. 0.0.24

    # Step 2: Determine new version (simulate or real)
    new_version_cmd = ["poetry", "version", args.type]
    if dry_run:
        print(f"[DRY-RUN] Would run: {' '.join(new_version_cmd)}")
        new_version = "<new-version>"
    else:
        run(new_version_cmd)
        new_version = run(["poetry", "version", "-s"])  # e.g. 0.0.25

    commit_message = f"release {new_version}"
    tag_name = f"v{new_version}"

    try:
        if dry_run:
            print(f"[DRY-RUN] Would git add pyproject.toml")
            print(f"[DRY-RUN] Would commit with message '{commit_message}'")
            print(f"[DRY-RUN] Would create git tag '{tag_name}'")
            print(f"[DRY-RUN] Would push commit and tag to origin")
        else:
            # Step 3: Commit changes
            run(["git", "add", "pyproject.toml"])
            run(["git", "commit", "-m", commit_message])

            # Step 4: Tag
            run(["git", "tag", tag_name])

            # Step 5: Push
            print(f"Pushing commit and tag '{tag_name}' to origin...")
            run(["git", "push", "origin", "HEAD"])
            run(["git", "push", "origin", tag_name])

        # Step 6: Poll PyPI (only if not dry-run)
        if not dry_run:
            wait_for_pypi(package_name, new_version)

        print(f"Done! Version {new_version} {'(dry run)' if dry_run else ''}")

    except subprocess.CalledProcessError as e:
        print("\nError occurred.")
        print(f"Command: {' '.join(e.cmd)}")
        if e.output:
            print(f"Output:\n{e.output}")
        if e.stderr:
            print(f"Error:\n{e.stderr}")

        if not dry_run:
            # Rollback if actual changes were made
            print("Rolling back changes...")
            run(["git", "checkout", "pyproject.toml"], check=False)
            run(["git", "reset", "--hard", old_commit], check=False)
            run(["git", "tag", "-d", tag_name], check=False)

        sys.exit(1)

if __name__ == "__main__":
    main()
