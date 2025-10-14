# publisher.py

"""PyPI package publishing module with local token support."""
import os
import sys
import re
import subprocess
import time
from typing import Optional, Tuple
from dotenv import load_dotenv

load_dotenv()


class PublisherError(Exception):
    """Base exception for publisher errors."""
    pass


class Publisher:
    """Handle PyPI package publishing workflow."""

    PYPI_API = "https://pypi.org/pypi"

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.original_commit = None

    def run_command(self, cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
        """Execute shell command."""
        if self.dry_run:
            print(f"[DRY-RUN] Would run: {' '.join(cmd)}")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        kwargs = {"check": check}
        if capture:
            kwargs.update({"capture_output": True, "text": True})

        return subprocess.run(cmd, **kwargs)

    def validate_clean_repository(self):
        """Check if git repository is clean."""
        print("Validating repository state...")
        # Always run validation, even in dry-run mode
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True
        )

        if result.stdout.strip():
            raise PublisherError(
                "Repository has uncommitted changes. "
                "Please commit or stash changes before releasing."
            )

    def validate_pyproject(self):
        """Check if pyproject.toml exists and is valid."""
        print("Validating pyproject.toml...")

        if not os.path.exists("pyproject.toml"):
            raise PublisherError(
                "pyproject.toml not found. "
                "This tool requires a Poetry-managed Python project."
            )

        # Always run validation, even in dry-run mode
        result = subprocess.run(
            ["poetry", "check"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            raise PublisherError(
                "Invalid pyproject.toml configuration. "
                f"Run 'poetry check' to validate.\n{result.stderr}"
            )

    def get_package_info(self) -> Tuple[str, str]:
        """Get package name and current version."""
        with open("pyproject.toml") as f:
            content = f.read()

        name_match = re.search(r'^name\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
        if not name_match:
            raise PublisherError("Could not extract package name from pyproject.toml")

        # Always run this for real, even in dry-run mode (read-only operation)
        result = subprocess.run(
            ["poetry", "version", "-s"],
            capture_output=True,
            text=True,
            check=True
        )
        version = result.stdout.strip()

        return name_match.group(1), version

    def get_new_version(self, bump_type: str) -> str:
        """Calculate new version after bump."""
        # Always run this for real, even in dry-run mode (read-only operation)
        result = subprocess.run(
            ["poetry", "version", bump_type, "--dry-run"],
            capture_output=True,
            text=True,
            check=True
        )

        match = re.search(r'from\s+\S+\s+to\s+(\S+)', result.stdout)
        if not match:
            raise PublisherError(f"Could not determine new version for bump type: {bump_type}")

        return match.group(1)

    def get_repo_info(self) -> str:
        """Extract repository owner/name from git remote."""
        # Always run this for real, even in dry-run mode (read-only operation)
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True
        )
        repo_url = result.stdout.strip()

        patterns = [
            r"^git@github\.com:(.+)/(.+)\.git$",
            r"^git@github\.com:(.+)/(.+)$",
            r"^https://github\.com/(.+)/(.+)\.git$",
            r"^https://github\.com/(.+)/(.+)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, repo_url)
            if match:
                return f"{match.group(1)}/{match.group(2)}"

        raise PublisherError(f"Unsupported git remote URL format: {repo_url}")

    def confirm_release(self, package_name: str, current_version: str, new_version: str, bump_type: str, skip_confirm: bool = False):
        """Show release details and prompt for confirmation."""
        print("\n" + "="*60)
        print("RELEASE DETAILS")
        print("="*60)
        print(f"  Package:  {package_name}")
        print(f"  Current:  {current_version}")
        print(f"  New:      {new_version}")
        print(f"  Type:     {bump_type}")
        print(f"  Mode:     {'DRY-RUN' if self.dry_run else 'LIVE'}")
        print("="*60)
        print("\nActions to be performed:")
        print("  1. Bump version in pyproject.toml")
        print("  2. Update poetry.lock file")
        print("  3. Build package with Poetry")
        print("  4. Publish to PyPI")
        print("  5. Commit version changes")
        print("  6. Create git tag v" + new_version)
        print("  7. Push commit and tag to origin")
        print("  8. Create GitHub release")
        print("  9. Wait for PyPI publication")
        print("="*60 + "\n")

        if self.dry_run:
            print("[DRY-RUN] Skipping confirmation prompt")
            return

        if skip_confirm:
            print("Proceeding with release (--yes flag set)...")
            return

        response = input("Proceed? (Y/n): ").strip().lower()
        if response and response != 'y':
            print("Release cancelled by user")
            sys.exit(0)

    def bump_version(self, bump_type: str):
        """Bump version using Poetry."""
        print(f"Bumping version ({bump_type})...")
        self.run_command(["poetry", "version", bump_type])

        print("Updating poetry.lock...")
        self.run_command(["poetry", "lock", "--no-update"])

    def build_package(self):
        """Build package with Poetry."""
        print("Building package...")
        self.run_command(["poetry", "build"])

    def publish_to_pypi(self):
        """Publish package to PyPI."""
        print("Publishing to PyPI...")

        token = os.getenv("PYPI_API_TOKEN")
        if not token:
            raise PublisherError(
                "PYPI_API_TOKEN environment variable not set. "
                "Please set your PyPI token in .env file or environment."
            )

        if self.dry_run:
            print("[DRY-RUN] Would publish to PyPI with token")
            return

        self.run_command([
            "poetry", "publish",
            "--username", "__token__",
            "--password", token
        ])

    def git_commit_and_tag(self, version: str):
        """Commit version changes and create tag."""
        print("Committing version changes...")
        self.run_command(["git", "add", "pyproject.toml", "poetry.lock"])
        self.run_command(["git", "commit", "-m", f"release {version}"])

        print(f"Creating tag v{version}...")
        self.run_command(["git", "tag", f"v{version}"])

        print("Pushing to origin...")
        self.run_command(["git", "push", "origin", "HEAD"])
        self.run_command(["git", "push", "origin", f"v{version}"])

    def create_github_release(self, version: str):
        """Create GitHub release using REST API."""
        print("Creating GitHub release...")

        token = os.getenv("GITHUB_TOKEN")
        if not token:
            print("Warning: GITHUB_TOKEN not set. Skipping GitHub release creation.")
            return

        if self.dry_run:
            print("[DRY-RUN] Would create GitHub release")
            return

        try:
            import requests

            repo = self.get_repo_info()
            tag_name = f"v{version}"

            # Get commits since last tag for release notes
            result = subprocess.run(
                ["git", "tag", "--sort=-creatordate"],
                capture_output=True,
                text=True,
                check=True
            )
            tags = result.stdout.strip().split('\n')
            previous_tag = tags[1] if len(tags) > 1 else None

            # Generate release notes from commits
            if previous_tag:
                result = subprocess.run(
                    ["git", "log", f"{previous_tag}..HEAD", "--pretty=format:- %s"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                release_notes = result.stdout.strip()
            else:
                release_notes = "Initial release"

            # Create release via GitHub API
            url = f"https://api.github.com/repos/{repo}/releases"
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            }
            data = {
                "tag_name": tag_name,
                "name": f"Release {tag_name}",
                "body": release_notes,
                "draft": False,
                "prerelease": False,
            }

            response = requests.post(url, json=data, headers=headers)

            if response.status_code == 201:
                print(f"✓ GitHub release created: {response.json()['html_url']}")
            else:
                print(f"Warning: GitHub release creation failed: {response.status_code}")
                print(f"  {response.json().get('message', 'Unknown error')}")

        except ImportError:
            print("Warning: requests library not available. Skipping GitHub release.")
        except Exception as e:
            print(f"Warning: GitHub release creation failed: {e}")

    def poll_pypi(self, package_name: str, version: str, max_retries: int = 12, interval: int = 5):
        """Wait for package to appear on PyPI."""
        if self.dry_run:
            print("[DRY-RUN] Would poll PyPI for publication")
            return

        print("Waiting for PyPI publication...")

        try:
            import requests

            for i in range(max_retries):
                spinner = "|/-\\"[i % 4]
                print(f"\rChecking PyPI {spinner}", end="", flush=True)

                try:
                    response = requests.get(f"{self.PYPI_API}/{package_name}/json", timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        latest_version = data.get("info", {}).get("version")

                        if latest_version == version:
                            print(f"\r✓ Version {version} published to PyPI!")
                            return
                except:
                    pass

                time.sleep(interval)

            print(f"\r⚠ Timeout waiting for PyPI publication")
            print(f"Check manually: https://pypi.org/project/{package_name}/")

        except ImportError:
            print("Warning: requests library not available. Skipping PyPI polling.")

    def rollback(self, version: Optional[str] = None):
        """Rollback changes on error."""
        if self.dry_run:
            return

        print("\nRolling back changes...")

        try:
            # Reset files
            subprocess.run(["git", "checkout", "pyproject.toml", "poetry.lock"],
                         capture_output=True, check=False)

            # Reset to original commit if we have it
            if self.original_commit:
                subprocess.run(["git", "reset", "--hard", self.original_commit],
                             capture_output=True, check=False)

            # Delete tag if created
            if version:
                subprocess.run(["git", "tag", "-d", f"v{version}"],
                             capture_output=True, check=False)

            print("✓ Rollback completed")
        except Exception as e:
            print(f"Warning: Rollback may be incomplete: {e}")

    def release(self, bump_type: str, skip_confirm: bool = False):
        """Execute full release workflow."""
        try:
            # Store original commit for rollback (always run, even in dry-run)
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True
            )
            self.original_commit = result.stdout.strip()

            # Validation
            self.validate_clean_repository()
            self.validate_pyproject()

            # Get package info
            package_name, current_version = self.get_package_info()
            new_version = self.get_new_version(bump_type)

            # Confirm
            self.confirm_release(package_name, current_version, new_version, bump_type, skip_confirm)

            if self.dry_run:
                print("\n[DRY-RUN] All checks passed. No changes made.")
                return

            # Execute release steps
            self.bump_version(bump_type)

            # Re-get version after bump
            _, new_version = self.get_package_info()

            self.build_package()
            self.publish_to_pypi()
            self.git_commit_and_tag(new_version)
            self.create_github_release(new_version)
            self.poll_pypi(package_name, new_version)

            # Success!
            print("\n" + "="*60)
            print(f"✓ Release {new_version} completed successfully!")
            print("="*60)
            print(f"  Package: https://pypi.org/project/{package_name}/{new_version}/")

            try:
                repo = self.get_repo_info()
                print(f"  Release: https://github.com/{repo}/releases/tag/v{new_version}")
            except:
                pass

            print("="*60)

        except PublisherError as e:
            print(f"\nError: {e}", file=sys.stderr)
            self.rollback(new_version if 'new_version' in locals() else None)
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            print(f"\nCommand failed: {' '.join(e.cmd)}", file=sys.stderr)
            if e.stderr:
                print(f"  {e.stderr}", file=sys.stderr)
            self.rollback(new_version if 'new_version' in locals() else None)
            sys.exit(1)
        except Exception as e:
            print(f"\nUnexpected error: {e}", file=sys.stderr)
            self.rollback(new_version if 'new_version' in locals() else None)
            sys.exit(1)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="PyPI package publisher")
    parser.add_argument(
        "bump_type",
        choices=["patch", "minor", "major"],
        help="Version bump type"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate release without making changes"
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt"
    )

    args = parser.parse_args()

    publisher = Publisher(dry_run=args.dry_run)
    publisher.release(args.bump_type, skip_confirm=args.yes)


if __name__ == "__main__":
    main()
