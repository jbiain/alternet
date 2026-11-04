# 006 — Licence decision (draft, not legal advice)

## Facts (upstream LICENSE text, checked 2026-11-04)
Reticulum is MIT plus two extra conditions:
1. It must not be used in a system whose functions include the ability to purposefully harm human beings.
2. It must not be used, "directly or indirectly", in the creation of an AI/ML/language-model training dataset,
   including any use that contributes to training or developing such a model.

Neither condition is OSI-approved, so Reticulum is source-available, not "open source" by the OSI definition.

## Why it matters for Alternet
- Alternet carries public text. Anyone may copy replicated pages into a training set. Whether that is
  "indirect use" of the carrier is unclear, and the clause is vague enough that a cautious user or distributor may refuse it.
- Alternet's stated goal includes people running their own LLMs. Serving a local model over a Reticulum-based
  network sits close to the clause.
- The "ability to do harm" clause is undefined. Distributors (Debian, Homebrew, app stores) often refuse such terms.
- One maintainer wrote nearly all the code; the licence can only be changed or excepted by that person.

## Options
| Option | Pros | Cons |
|---|---|---|
| A. Keep Reticulum as the only carrier | Works today, multi-transport | Inherits both clauses; blocks distro packaging |
| B. Ask the author for a written exception | Cheap, may work | Slow, may be refused, depends on one person |
| C. Reticulum as an optional carrier; add a second carrier (plain TCP/QUIC, then Iroh or libp2p) | Core stays clean; no lock-in | Costs build time; loses LoRa/serial until a replacement exists |
| D. Replace Reticulum entirely | Clean licence | Loses its low-bandwidth transports |

## Owner's reading (2026-11-04)
Alternet does not itself harm people or train models, so its own use of Reticulum looks outside both clauses. That is a reasonable
reading. The residual risk is the vague wording ("directly or indirectly", "contributes to") and that downstream users or
distributors may not want to take it on. Because Reticulum stays an optional, separately installed carrier under its own licence,
Alternet's Apache-2.0 code is not affected either way. The README must say so.

## Reticulum README warning (read 2026-11-04)
The upstream README warns against "LLM-generated" reimplementations, guides and apps derived from the RNS source or docs, calls
licence grants on such derivatives "void", and says downstream users are personally liable. It also says the protocol was dedicated to the
public domain in 2016 and only the reference implementation carries the Reticulum License. Alternet imports the real `rns` package
and copies none of its code, so it is not a reimplementation, but much of our code was AI-written and the RNS source was read while
debugging. Keep Reticulum unvendored and separate, and put this point to a lawyer before any public release.

## Decision (owner, 2026-11-04)
- Alternet's own code: **Apache-2.0** (LICENSE file added at the repo root).
- **Never vendor Reticulum.** It is not copied into the repo and not a required dependency; it is an optional carrier the
  user installs separately (`pip install rns`). The repo ships none of its code.
- **Add a plain TCP carrier next** so the network runs with no Reticulum at all. Then Reticulum is just one plug-in.
- **Do not contact the Reticulum author.** The project avoids the question by not depending on or distributing Reticulum.
- A lawyer's read is still advisable before wide public release (optional-plugin use of third-party code is generally
  low risk, but this is an engineer's reading, not legal advice).

## Consequences / to do
1. Move `rns` from `dependencies` to an optional extra (`pip install alternet[reticulum]`) in `core/pyproject.toml`.
2. Define a small carrier interface (listen, connect, request/response, peer identity) and wrap Reticulum behind it.
3. Build the TCP carrier: Ed25519-authenticated, encrypted handshake (Noise-style), same manifest/block requests.
4. README: say Reticulum is optional and under its own licence.
5. Later: Iroh or libp2p for NAT traversal. LoRa/serial stay Reticulum-only until another carrier exists.

## Update (owner, later on 2026-11-04)
Decision revised: **keep Reticulum as the main carrier** (radio/serial reach and a proven relay layer). The plain TCP carrier is
no longer scheduled; it stays an optional, lower-priority idea. Everything else above stands: Apache-2.0 for our code, Reticulum never
vendored, installed separately under its own licence, core kept carrier-independent so a swap stays possible.

## Decision status
Accepted (revised).
