# 009 — Strategy: positioning, wedge, and the first real test

## What's actually built (2026-11-04)
Identity, local discovery, encrypted connections (Reticulum), signed content-addressed sites, sync between
nodes, a private-sites allowlist, a public relay (178.128.165.25), petnames, a read-only browser gateway, and
a BBS-style terminal browser (full curses on Mac/Linux, a live arrow-key renderer on iOS via termios, a plain
fallback everywhere). All verified on real devices across Wi-Fi, hotspot, mobile data, and the relay. See
`spike/reticulum/RESULTS.md` for every test and `005`/`006` for the carrier and licence decisions.

## Positioning
The pitch that tested well in conversation: **a network no one controls, that works without internet, with
two real ways to experience it on the same signed content** — a terminal BBS (native, works anywhere Python
runs) and an ordinary browser (via a local or relay gateway, read-only, nothing to install). Content survives
its publisher going offline, because a trusted peer's verified copy serves it.

What we are not claiming: city-wide mesh reach from phones (cellular and Wi-Fi don't allow that; see
`008-other-links.md`), video streaming at scale (bandwidth-gated, staged for later), or anonymity.

## The wedge
Self-hosters and terminal/BBS enthusiasts first (`002-problem-statement.md`), with a concrete first use case:
a small group (5-20 people) sharing a text site or zine that stays readable when any one member's machine is
off. This is the smallest thing that proves the actual differentiator (survives host loss, no account, no
server rented) rather than a generic "cloud alternative" pitch nobody needs yet.

## The real test (30 days from today, target: 2026-12-04)
Recruit three people outside this project. Success = all three install it, read each other's sites, and keep
a node running for at least a week, with no hand-holding beyond the README. Track every point of friction
(install, discovery, understanding what a site id is, petnames, pinning) as the actual roadmap — rough edges
found this way outrank anything speculative in this document.

## What must exist before inviting anyone
- One-command install (today: `pip install -e core/`; good enough for self-hosters, not for "ordinary computer
  user" — acceptable for this audience).
- A stable, always-on relay: done (VPS, hardened, auto-updating).
- Seed content so a newcomer sees something on day one: the BBS site now serves this; needs more than one
  board before real users arrive.
- Licence clarity: done (`006`) — Apache-2.0 for our code, Reticulum kept optional and unvendored.

## Deferred, not abandoned
Background service (node starts with the OS, no "server" to run by hand), broadcast/station format (signed
append-only stream — the "radio" idea), readable names beyond petnames (signed directories, `007`), encrypted
private content at rest, key rotation/revocation, LoRa and other non-IP carriers (`008`).

## Decision status
Proposed. The 30-day outside-user test is the next concrete milestone; everything else in this document is
subordinate to what that test actually finds.
