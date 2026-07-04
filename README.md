# ci — shared reusable CI for the Bussetech Software Studio

Public home of the studio's **self-contained reusable workflows**, callable by
every studio repo — **public or private**. This repo is public on purpose: a
public caller (the portal `www`, the `theme`, public projects) cannot resolve a
reusable workflow stored in a *private* repo, so the shared site/data CI lives
here rather than in the private control repo (`platform`). See
`platform/docs/decisions/ADR-0011`.

## Workflows

- **`reusable-site-ci.yml`** — Jekyll build → internal link check (lychee) →
  HTML validation → discoverability → source-leak check (`private-published`) →
  artifact.
- **`reusable-data-ci.yml`** — JSON/YAML/CSV schema validation + a repo-provided
  referential-integrity hook.

Both are **self-contained** (pinned tools + stdlib Python inline): they check
out only the caller and need no token or second checkout, so they run in or out
of the org.

> Gnome CI (`reusable-gnome-ci.yml`) stays in `platform` — it is coupled to the
> private gnome harness (`bin/gn-run`, `schema/`) and its callers are gnome
> repos that already hold the App token.

## Use it (thin caller stub)

```yaml
# .github/workflows/ci.yml in a site/data repo
name: ci
on: { push: { branches: [main] }, pull_request: {} }
permissions: { contents: read }
jobs:
  site:
    uses: bussetech/ci/.github/workflows/reusable-site-ci.yml@v1
    with:
      visibility: public          # public | private | private-published
  data:
    uses: bussetech/ci/.github/workflows/reusable-data-ci.yml@v1
```

Pin to **`@v1`** (a moving major tag), never `@main`. Inputs, the data manifest
format, the UAT config, and the escalation ladder are documented in
`platform/docs/testing.md`.

## Versioning

`v1` moves to the latest backward-compatible commit
(`git tag -f v1 <sha> && git push -f origin v1`); a breaking change cuts `v2`.
`selftest.yml` proves both workflows against the fixtures in `tests/fixtures/`
on every push.

## Detach

Fully standalone: the reusable workflows carry their own checkers and reference
nothing in `platform`. To re-home, transfer the repo and re-point callers at
`<owner>/ci/...@vN`. Its only studio binding is its registration in
`platform/platform.yml`.
