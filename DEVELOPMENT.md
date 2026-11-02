# storyblok-updater, development notes

## What this folder is
A small Python client and CLI for the Storyblok Management API, for editing pages and
posts in any client's space. It is client-neutral.

## Layout

    sb_client.py        SBClient (network calls) and pure helpers (paths, diff, clone)
    cli.py              command line: ping, list, get, show, set, clone, push
    test_sb_client.py   offline tests for the pure helpers, no token needed
    README.md           setup and usage

## Rules
- Credentials are `{PREFIX}_STORYBLOK_TOKEN`, `{PREFIX}_STORYBLOK_SPACE`,
  `{PREFIX}_STORYBLOK_REGION` in `.env`. Never put a token in a file
  that is committed to git, or into any settings or config file.
- Writes stay dry-run by default and draft by default. Do not change either default.
- Never invent field paths, ids or uuids. Run `show` on a real story first.
- Run `python test_sb_client.py` after any change to sb_client.py.
- Add a helper to sb_client.py and a test for it before using it from cli.py.
- Client-specific rules (which fields mean what, per-language conventions) go in that
  client's own folder, not here.

## Open items
- `set`, `clone` and `push` have not yet run against a live space (offline tests only).
  Record the first live run here once done.
- Decide whether to add a markdown-to-rich-text converter once the client's page
  structure is known.
