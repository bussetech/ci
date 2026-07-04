# CLAUDE.md — ci (shared reusable CI)

Public home of the studio's reusable **site** and **data** CI workflows,
callable by every repo (public or private). It exists because a public caller
cannot resolve a reusable workflow in the private `platform` repo (Team plan has
no `internal` visibility) — see `platform` ADR-0011. Gnome CI stays in
`platform`.

## Read first

- `README.md` — what's here and how to call it.
- `platform/docs/testing.md` — the studio-wide testing conventions (caller
  stubs, data manifest, UAT, escalation ladder, versioning). This repo is one
  half of that story.

## Rules

- **Self-contained workflows.** Both reusable workflows carry their checkers
  inline (pinned binaries + stdlib Python). Do not add a dependency on
  `platform` (no `platform.yml`, no `bin/gn-run`) — that coupling is exactly what
  this repo avoids so public callers work.
- **Supply chain.** Third-party Actions pinned to full commit SHAs; pinned tools
  (lychee) verified by version+sha256 — same discipline as the rest of the org.
- **Prove before tagging.** `selftest.yml` runs both workflows against
  `tests/fixtures/` on every push. Keep it green.
- **Versioning.** Consumers pin `@v1` (moving major tag). Backward-compatible
  change → move `v1` (`git tag -f v1 <sha> && git push -f origin v1`); breaking
  change → cut `v2` and migrate callers. Prefer additive (new optional inputs).
- Conventional commits, atomic.

## Detach procedure (repo portability)

Standalone by design — the workflows reference nothing in the studio. Transfer
the repo, re-point callers at `<owner>/ci/...@vN`. Its only studio binding is
its registration in `platform/platform.yml`.
