# Releasing terminaide

Releases are fully automated. The only manual acts are: bump the version,
write the changelog, push a tag.

## One-time setup (already done once, listed here for reference)

The release pipeline publishes to PyPI via **trusted publishing** (OIDC) —
no API token is stored anywhere. It requires a one-time registration on
pypi.org (*terminaide project → Publishing → Add trusted publisher*):

| Field | Value |
|---|---|
| Owner | `basileaw` |
| Repository | `terminaide` |
| Workflow filename | `release.yml` |
| Environment | *(blank — no approval gate; a pushed tag is the intent)* |

These must match the workflow file byte-for-byte or publish will fail with
an OIDC error.

## Releasing a version

1. Bump `version` in `pyproject.toml`.
2. Add a `## X.Y.Z` section to `CHANGELOG.md`.
3. Commit both (e.g. `release: vX.Y.Z`), then:

   ```bash
   git tag vX.Y.Z
   git push origin main vX.Y.Z
   ```

4. The [Release workflow](.github/workflows/release.yml) then, automatically
   and in order:
   - refuses to run if the tag doesn't match `pyproject.toml`'s version,
   - runs the **full test suite** — a red suite cannot ship,
   - builds the wheel + sdist,
   - creates the **GitHub Release** marked latest, with notes extracted
     from the changelog section,
   - publishes to **PyPI** via trusted publishing.

## Notes

- Tag, GitHub Release, and PyPI artifact are all produced from the same
  commit by construction — the tag you push is the artifact you get.
- Local `poetry publish` remains possible alongside, but should be
  unnecessary.
- CI runs the same suite on every PR and push to `main`, so a release tag
  is never the first time the suite runs on Linux.

## Dependency updates (fully automated)

The pieces and why each exists — removing one breaks the chain:

| Piece | Role |
|---|---|
| `.github/dependabot.yml` | Opens grouped PRs: minor/patch grouped per ecosystem, majors grouped separately |
| `.github/workflows/ci.yml` | The `test` check that gates every PR |
| `main` branch protection | Makes `test` **required** (and `strict`, so PRs must be current) — without this, auto-merge has nothing to queue against |
| Repo settings | `allow_auto_merge` + `delete_branch_on_merge` (Settings → General → Pull Requests) |
| `.github/workflows/dependabot-auto-merge.yml` | On a Dependabot PR: rebase if behind, label majors, otherwise arm squash auto-merge |
| `.github/workflows/dependabot-sweep.yml` | Daily: rebase anything that went behind and re-arm lost auto-merges |

Rules of the road:

- **Minor/patch auto-merge** once `test` is green. **Majors never
  auto-merge** — they get the `major-bump` label and wait for a human,
  because a major can change behaviour while tests stay green.
- Only PRs authored by `dependabot[bot]` **from this repository** are acted
  on. Fork PRs get a read-only token by design and are ignored.
- Auto-merge uses `GITHUB_TOKEN`, so the merge it performs does **not**
  trigger further workflows. That is fine here: nothing needs to run after
  a merge, and the release pipeline triggers on tag push, not on merge.
- A PR that touches `.github/workflows/` cannot be armed by `GITHUB_TOKEN`
  (it may not hold the `workflows` permission). Those need a manual merge;
  the sweep will leave them alone rather than failing.
- If Dependabot PRs pile up again, check branch protection first: `strict`
  required checks mean a PR behind `main` can never merge, and only an
  explicit rebase fixes it (which the sweep does daily).
