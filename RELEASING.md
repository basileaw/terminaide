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
