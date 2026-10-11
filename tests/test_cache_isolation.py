"""Per-process cache isolation.

Generated wrappers live in ``cache/pid/<pid>/`` rather than a single shared
``cache/scripts/``. The shared layout caused a cross-process race: starting
any second terminaide process deleted the wrappers a running server's ttyd
was still executing, producing

    Error: Script not found: .../cache/scripts/monitor_read_standalone.py

These tests pin the isolation guarantee itself, not just the paths, so the
race cannot silently return.
"""

import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from terminaide.core.wrappers import (
    _process_cache_root,
    cleanup_orphaned_process_dirs,
    cleanup_stale_ephemeral_files,
    get_ephemeral_dir,
    get_params_dir,
    iter_process_cache_dirs,
    write_wrapper_file,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(code: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT), **(env or {})},
    )


def test_cache_dirs_are_namespaced_by_pid():
    assert str(os.getpid()) in str(get_ephemeral_dir())
    assert str(os.getpid()) in str(get_params_dir())
    assert "pid" in _process_cache_root().parts


def test_scripts_and_params_share_one_namespace():
    root = _process_cache_root()
    assert get_ephemeral_dir().parent == root
    assert get_params_dir().parent == root


def test_cleanup_only_touches_own_namespace():
    """The per-process cleanup removes our files, never another process's."""
    ours = get_ephemeral_dir()
    write_wrapper_file(
        ours / "ours_should_go.py", "# ours\n", register_for_cleanup=False
    )

    # A namespace belonging to a DIFFERENT, still-alive process (ppid is a
    # safe stand-in: it exists and is not us).
    other_pid = os.getppid()
    other = _process_cache_root().parent / str(other_pid) / "scripts"
    other.mkdir(parents=True, exist_ok=True)
    other_wrapper = other / "theirs_must_survive.py"
    other_wrapper.write_text("# theirs\n")

    try:
        cleanup_stale_ephemeral_files()
        assert other_wrapper.exists(), "another process's wrapper was deleted"
    finally:
        shutil.rmtree(other.parent, ignore_errors=True)


def test_live_process_wrapper_survives_another_process_starting():
    """The regression itself.

    A server holding a live wrapper must not lose it when a second
    terminaide process boots and runs its startup cleanup.
    """
    holder = textwrap.dedent(
        """
        import sys, time
        from terminaide.core.wrappers import get_ephemeral_dir, write_wrapper_file
        p = get_ephemeral_dir() / "monitor_read_standalone.py"
        write_wrapper_file(p, "# live\\n", register_for_cleanup=False)
        print(str(p), flush=True)
        time.sleep(60)
        """
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", holder],
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    try:
        wrapper = Path(proc.stdout.readline().strip())
        assert wrapper.exists()

        # A different process boots and runs its startup cleanup.
        result = _run(
            """
            from terminaide.core.wrappers import cleanup_stale_ephemeral_files
            cleanup_stale_ephemeral_files()
            """
        )
        assert result.returncode == 0, result.stderr

        assert wrapper.exists(), (
            "a live process lost its wrapper when another process started up"
        )
    finally:
        proc.terminate()
        proc.wait()
        cleanup_orphaned_process_dirs(max_age_seconds=0)


def test_orphaned_namespace_is_reclaimed():
    """A dead pid's namespace is cleaned up so the cache does not grow."""
    dead = _process_cache_root().parent / "999998" / "scripts"
    dead.mkdir(parents=True, exist_ok=True)
    (dead / "leftover.py").write_text("# orphan\n")

    # max_age_seconds=0 also reclaims namespaces whose pid looks alive,
    # which keeps the test independent of pid reuse on the host.
    cleanup_orphaned_process_dirs(max_age_seconds=0)

    assert not (dead.parent).exists(), "orphaned namespace was not reclaimed"


def test_orphan_sweep_never_removes_our_own_namespace():
    ours = get_ephemeral_dir()
    ours.mkdir(parents=True, exist_ok=True)
    marker = ours / "keep_me.py"
    marker.write_text("# keep\n")

    cleanup_orphaned_process_dirs(max_age_seconds=0)

    assert marker.exists(), "the sweep removed the running process's own namespace"


def test_iter_process_cache_dirs_includes_own_and_others():
    other = _process_cache_root().parent / "999997" / "params"
    other.mkdir(parents=True, exist_ok=True)
    try:
        dirs = iter_process_cache_dirs()
        assert get_params_dir() in dirs
        assert other in dirs
        assert dirs[0] == get_params_dir(), "own namespace should come first"
    finally:
        cleanup_orphaned_process_dirs(max_age_seconds=0)
