# Changelog

## 2.0.0 — Security hardening release

A full security review drove this release. The headline: **unauthenticated terminals are now impossible by construction when the server is exposed**, while local development stays exactly as frictionless as before.

### Breaking changes (deliberate default flips)

- **ttyd backends bind `127.0.0.1` by default** (was `0.0.0.0`). Terminal traffic only flows through the proxy; direct network access to the ttyd ports — which bypassed all proxy-level protections — is gone. Opt back in with `ttyd_options.interface` if you truly need direct ttyd access.
- **Direct-serve modes (`serve_script`/`serve_function`) bind `127.0.0.1`** (was hardcoded `0.0.0.0`). Pass `host="0.0.0.0"` to expose — and see the next item.
- **Terminal token authentication** (`core/auth.py`, Jupyter model): a server bound beyond loopback without credentials gets an auto-generated session token, required on all terminal routes and printed to the console as a ready-to-click URL. Set your own via `auth_token=` or `TERMINAIDE_TOKEN`; `auth_token=""` explicitly disables (loud warning); ttyd `-c` credentials also satisfy auth. `serve_apps` takes a `host` declaration (default `"0.0.0.0"` — conservative: terminaide cannot detect your uvicorn bind). **If you currently expose terminals without your own auth, add `auth_token=` or expect your users to need the printed token.**
- **`/health` returns `{"status": "ok"}` by default.** The full payload (script paths, ports, PIDs, route topology) is opt-in via `health_verbose=True` or `TERMINAIDE_HEALTH_VERBOSE=1`.
- **FastAPI floor raised to `>=0.141`** (carries starlette 1.x security fixes). Requires Python 3.12+ as before.
- **`bs4`, `readchar`, `h11`, `httpcore` removed from dependencies** (bs4/readchar were never imported; h11/httpcore were pure transitives). If your own code relied on terminaide's environment providing them, declare them yourself.

### Security fixes

- **Port conflicts never SIGKILL foreign processes.** Only leftover ttyd processes spawned from the terminaide-managed binary are killed (zombie cleanup preserved); anything else produces a clear `TTYDStartupError` naming the PID. Port-in-use detection switched from connect-testing to bind-testing (connect tests report full-backlog listeners as free).
- **ttyd downloads are pinned and verified**: fixed version with embedded SHA-256 digests, atomic install, no partial/unverified files left behind, tarball extraction with the `data` filter. Runtime "latest version" GitHub API resolution removed (also removes a network call on every startup).
- **Dynamic-route parameter races eliminated**: per-connection parameter files (uuid, atomic writes) consumed via an atomic FIFO claim queue — no more cross-session parameter leakage or lost arguments between concurrent connections.
- **Proxy hygiene**: hop-by-hop headers and cookies no longer forwarded to ttyd (`Authorization` deliberately kept for ttyd `-c`); `TRACE` rejected; HTML pages carry `X-Content-Type-Options`, `Referrer-Policy`, and `X-Frame-Options: SAMEORIGIN` (embedding opt-in via `allow_embedding=True`).
- **Per-IP WebSocket rate limiting** (default 30 connections/minute, `ws_rate_limit_per_minute` to tune, `None` to disable) — every WS connection spawns a ttyd child process.
- **The auth token never reaches terminal argv/parameter files**, and unauthenticated terminals inheriting credential-looking environment variables produce a startup warning (names only).
- Fixed root-mounted `/health` registering at `//health` (unreachable).
- Fixed a startup race where the proxy dialed ttyd before its listener was ready (now retried ~2s).

### Dependencies

- fastapi 0.141 / starlette 1.6 (5 advisories), urllib3 2.7.0 (4 high), requests removed from tests (httpx), plus idna/pygments/python-dotenv/pytest updates — **all 17 open Dependabot alerts cleared**, and the dependency tree reduced from 43 to 34 locked packages.
- Range policy: `>=X,<N` instead of carets for 0.x packages (poetry carets pin the 0.x minor, which had blocked starlette security fixes).
- `deptry` added (`poe audit-deps`) to catch dead/undeclared dependencies — the structural fix for the unused-dependency rot this review uncovered.

### Upgrade notes

- Local development: **nothing changes** — loopback serving needs no token and behaves exactly as before.
- Exposed deployments: set `auth_token` (or read the printed/generated one), terminate TLS in front, and see the new **Cloud & Container Deployment** section in the README (IMDSv2, security groups, `forward_env` scoping).
- Anything parsing the old verbose `/health` should set `health_verbose=True` or `TERMINAIDE_HEALTH_VERBOSE=1`.

## 1.4.8 and earlier

See `git log` — releases prior to 2.0.0 were not tracked in this changelog.
