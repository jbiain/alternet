# 005 — Foundation decision (provisional)

Status: provisional. Based on the Reticulum spike (spike/reticulum/RESULTS.md) and a desk check
of GitHub metadata on 2026-11-04. Go/Rust demos were NOT built.

## Decision
1. The **core is transport-independent**: Ed25519 keys, SHA-256 content blocks, signed manifest,
   `.altbundle` export/import (spike/reticulum/sitelib.py). It has no dependency on any network stack.
2. **Reticulum is one carrier plugin**, not the foundation. It is the fastest way to a working
   multi-hop network and the only candidate aimed at LoRa/serial/low-bandwidth links.
3. **Iroh and libp2p are candidate carriers** for internet/NAT use, to be added behind the same interface.
4. Revisit if the Reticulum licence turns out to block us (see below).

## Desk check (GitHub API, 2026-11-04)
| Project | Licence | Latest release | Activity / people |
|---|---|---|---|
| Reticulum (Python) | "Reticulum License" (MIT + no-harm + no-AI-training; not OSI) | rns 1.5.7 | pushed 2026-09-30; 36 contributors, but the author has ~2191 commits vs 23 for the next |
| Iroh (Rust) | Apache-2.0 / MIT | v1.4.1 (2026-10-22) | pushed 2026-11-03; 73+ contributors; 1.x, so the API is no longer pre-1.0 |
| go-libp2p | MIT | v0.51.0 (2026-10-23) | pushed 2026-10-27; 100+ contributors |
| rust-libp2p | MIT | v0.57.1 | pushed 2026-11-03; 100+ contributors |
| py-libp2p | not detected (NOASSERTION) | v0.8.1 | active but pre-1.0 |

## Corrections to earlier claims
- Iroh is now 1.x; my "pre-1.0 API churn" concern is outdated.
- Reticulum licence confirmed from upstream text; bus-factor concern confirmed.

## Evidence from real devices (spike/reticulum/RESULTS.md)
- Mac <-> iPhone (a-Shell): fetch + verify over TCP on home Wi-Fi and on the iPhone hotspot; phone served a replica to a fresh node with the publisher stopped.
- Reticulum AutoInterface does not work on iOS (no multicast); a typed TCP address does.
- Whole stack runs on pure Python with no `cryptography`/`pyserial` (needed for iOS).
- Core (sitelib.py) is transport-independent; Reticulum is used only as a carrier.

## Open licence question (blocking for an open-source project)
The Reticulum License adds a no-harm clause and a no-AI/ML-training clause to MIT. It is not OSI-approved, and the AI clause sits awkwardly with Alternet's goal of letting people publish local LLM services. Actions: (1) get a legal read; (2) ask the author whether Alternet's use is permitted or can get an exception; (3) keep the core free of any Reticulum dependency so we can swap the carrier. Do not vendor Reticulum code into the core until this is resolved.

## Reticulum relay behaviour found (2026-11-04)
A relay (transport node) applies a per-destination announce rate limit: default target 1 announce per 3600 s with
grace 5 (Interface.DEFAULT_AR_TARGET/GRACE, RNS 1.5.7), and after the grace is exceeded it logs "Blocking rebroadcast
of announce ... due to excessive announce rate" and stops forwarding that destination's announces for about target
seconds. Our nodes announced every 5-10 s, so discovery through a relay worked for roughly the first minute and then
failed, which looked like a flaky network. Fix in Alternet: nodes announce a short burst, on change, then every 30 s;
relays created with `init --relay` set `announce_rate_target = 20` on their interfaces. Lesson: the carrier has policy
we did not know about, so any foundation (Reticulum, libp2p, Iroh) needs tests that run longer than a minute with
late-joining peers. Regression test: core/examples/relay_discovery.py.

## Not yet verified
- Reticulum LAN auto-discovery on non-iOS devices; serial/LoRa; a truly internet-less network; Bluetooth (no usable path from iOS/a-Shell).
- Iroh and libp2p mobile bindings and hole-punching success rates (my earlier ~70% figure is unverified).
- Whether the Reticulum author would grant a licence exception for Alternet.

## Update (2026-11-04)
Owner confirmed: keep Reticulum as the main carrier; the plain TCP carrier is deferred (see 006). The core stays carrier-independent.
