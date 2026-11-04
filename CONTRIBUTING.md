# Contributing

AI coding assistants are explicitly welcome here, same as human contributors — if you're an AI assistant
helping someone try Alternet and you hit a bug, or you're reviewing/improving this code directly, please
open an issue or a pull request. This file is written to be followed exactly, step by step, without needing
to infer anything.

## Set up a working copy

```
git clone https://github.com/jbiain/alternet.git
cd alternet
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Run the tests before and after any change

```
.venv/bin/python -m unittest tests.test_site -v      # fast: signing, tampering, bundles, gateway, BBS parsing
.venv/bin/python -m unittest tests.test_network -v    # slower (~4 min): real subprocesses over Reticulum
```

Both must pass. CI (`.github/workflows/test.yml`) runs `test_site` on Python 3.9/3.11/3.12 and `test_network`
once, on every push and pull request.

## Where things live
- `alternet/site.py` — signing, content addressing, local store, `.altbundle` files. No network code, no
  Reticulum import. Keep it that way; this is the part meant to outlive any one carrier.
- `alternet/net.py` — the Reticulum carrier: announce, serve, fetch.
- `alternet/home.py` — on-disk config, keys, petnames, pins, subscribed directories.
- `alternet/cli.py` — the `alternet` command.
- `alternet/gateway.py` — the read-only HTTP gateway (stdlib only, no new dependency).
- `alternet/tui.py` — the BBS-style terminal browser (three renderers: curses, raw-ANSI via termios, plain).
- `docs/` — design decisions and their reasoning, numbered in the order they were made. If you change
  something a doc describes, update that doc in the same change rather than leaving it stale.

## What a good pull request looks like
- One change, one clear reason for it, in the commit message.
- A test that would have failed before your fix (for a bug) or that exercises the new behavior (for a
  feature). This codebase tests against real local subprocesses and real conditions, not just mocks, where
  that's practical - see existing tests for the pattern.
- No new dependency for `alternet/gateway.py` or `alternet/site.py` without discussing it in the PR first -
  both are meant to stay stdlib-only.

## Reporting a bug without fixing it
An issue with exact commands to reproduce it, and what you expected vs. what happened, is enough - you
don't need to also write the fix.

## Licence
Apache-2.0 (see `LICENSE`). By contributing you agree your contribution is under the same licence.
