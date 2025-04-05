#!/usr/bin/env python3

import argparse
import subprocess
import sys

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

def main():
    parser = argparse.ArgumentParser(description="Bump version, commit, tag, and push.")
    parser.add_argument("type", choices=["patch", "minor", "major"], help="Version bump type.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without making changes.")
    args = parser.parse_args()

    dry_run = args.dry_run

    # Step 1: Check for clean git state
    status = run(["git", "status", "--porcelain"], check=False)
    if status:
        print("Error: Repository has uncommitted changes. Commit or stash them first.")
        sys.exit(1)

    # Record current state for rollback (not strictly needed for dry run)
    old_commit = run(["git", "rev-parse", "HEAD"])
    old_version = run(["poetry", "version", "-s"])

    # Step 2: Determine new version
    new_version_cmd = ["poetry", "version", args.type]
    if dry_run:
        print(f"[DRY-RUN] Would run: {' '.join(new_version_cmd)}")
        new_version = "<new-version>"
    else:
        run(new_version_cmd)
        new_version = run(["poetry", "version", "-s"])

    tag_name = f"v{new_version}"
    commit_message = f"release {new_version}"

    try:
        if dry_run:
            print(f"[DRY-RUN] Would git add pyproject.toml")
            print(f"[DRY-RUN] Would commit with message: '{commit_message}'")
            print(f"[DRY-RUN] Would create git tag: {tag_name}")
            print(f"[DRY-RUN] Would push commit and tag to origin")
        else:
            run(["git", "add", "pyproject.toml"])
            run(["git", "commit", "-m", commit_message])
            run(["git", "tag", tag_name])
            print(f"Pushing commit and tag '{tag_name}' to origin...")
            run(["git", "push", "origin", "HEAD"])
            run(["git", "push", "origin", tag_name])

        print(f"Success! Version {new_version} {'(dry run)' if dry_run else ''}")

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
