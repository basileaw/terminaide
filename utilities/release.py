#!/usr/bin/env python3

import argparse
import subprocess
import sys

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

def main():
    parser = argparse.ArgumentParser(description="Bump version, commit, tag, and push.")
    parser.add_argument("type", choices=["patch", "minor", "major"], help="Version bump type.")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without pushing changes.")
    args = parser.parse_args()

    dry_run = args.dry_run

    # Step 1: Check for clean git state
    status = run(["git", "status", "--porcelain"], check=False)
    if status:
        print("Error: Repository has uncommitted changes. Commit or stash them first.")
        sys.exit(1)

    # Record current commit to enable rollback
    old_commit = run(["git", "rev-parse", "HEAD"])

    try:
        # Step 2: Version bump
        old_version = run(["poetry", "version", "-s"])
        run(["poetry", "version", args.type])
        new_version = run(["poetry", "version", "-s"])

        # Step 3: Commit changes
        run(["git", "add", "pyproject.toml"])
        commit_message = f"release {new_version}"
        run(["git", "commit", "-m", commit_message])

        # Step 4: Create tag
        tag_name = f"v{new_version}"
        run(["git", "tag", tag_name])

        # Step 5: Push if not dry run
        if dry_run:
            print(f"[DRY-RUN] Would push commit and tag '{tag_name}' to origin.")
        else:
            print(f"Pushing commit and tag '{tag_name}' to origin...")
            run(["git", "push", "origin", "HEAD"])
            run(["git", "push", "origin", tag_name])

        print(f"Success! Version {new_version} is committed and tagged as {tag_name}.")

    except subprocess.CalledProcessError as e:
        print("\nError occurred, rolling back changes...")
        print(f"Command: {' '.join(e.cmd)}")
        if e.output:
            print(f"Output:\n{e.output}")
        if e.stderr:
            print(f"Error:\n{e.stderr}")

        # Rollback steps
        print("Resetting pyproject.toml...")
        run(["git", "checkout", "pyproject.toml"], check=False)

        print("Resetting commit...")
        run(["git", "reset", "--hard", old_commit], check=False)

        if 'new_version' in locals():
            print("Deleting tag...")
            run(["git", "tag", "-d", f"v{new_version}"], check=False)

        print("All changes rolled back. Exiting with error.")
        sys.exit(1)

if __name__ == "__main__":
    main()
