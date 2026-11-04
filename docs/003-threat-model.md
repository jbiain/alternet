# 003 — Threat Model (draft, v0.1 scope)

## Assets
- Node private key (identity).
- Published content integrity and authorship.
- The owner's local files, ports and CPU (must not be exposed).
- The trusted-peers list.
- Availability of replicated sites.

## Adversaries
| Adversary | Capability |
|---|---|
| Passive network observer | Sees traffic on LAN/internet |
| Active network attacker | Injects, replays, modifies traffic; spoofs discovery |
| Untrusted peer | Connects, floods requests, serves bad data |
| Malicious publisher | Publishes harmful or illegal content, impersonates others |
| Thief of a device | Reads key file from disk |
| Curious replica holder | Reads content that was meant to be private |

## Trust boundaries
Network ↔ node; node ↔ local filesystem; trusted peer ↔ unknown peer; publisher ↔ replica holder.

## Mitigations (v0.1)
| Threat | Mitigation |
|---|---|
| Eavesdropping | All connections encrypted and authenticated by node key. |
| Spoofed discovery (mDNS) | Discovery is only a hint; identity is verified in the handshake. |
| Unknown peers accessing services | Allowlist: no service reachable until a peer is explicitly trusted. |
| Tampered blocks | Every block verified against its content hash. |
| Forged or replaced site | Manifest signed by the owner key; version numbers prevent silent rollback; replicas verify before serving. |
| Impersonation | Identity is the public key. Display names are never trusted. |
| Resource abuse | Per-peer rate limits, size caps on manifests/blocks, storage quota. |
| Exposed local files | Sites are explicit directories packed at publish time. No path traversal on read; no filesystem access over the protocol. |
| Key theft | Key file mode 0600; optional passphrase encryption (planned). |
| Key loss | Out of scope for v0.1: documented backup procedure only. Rotation/revocation specified, not built. |
| Hosting bad content | Pinning is opt-in per site. Operators can unpin, delete and block publishers locally. |

## Findings from the spike (2026-11-04)
- Verified by tests: tampered block, tampered manifest, swapped owner key, version rollback and a tampered bundle are all rejected before anything is stored or served.
- **Allowlist implemented (2026-11-04):** sites can be `private` (signed `access` field). Private manifests and blocks are served only to peers whose node identity is in the owner's trusted list; untrusted peers get the same answer as "not found"; private sites are not announced; revocation is immediate. Tested in core/examples/private_site.py. Public sites remain open to anyone who can reach the node.
- **Gap:** private content is not encrypted at rest, and trusted replica holders see it in plain text. Trust is per node identity, not per person. A reader reveals its peer id to each holder.
- **Gap:** no per-site peer lists (trust is global to the node) and no way to revoke what a peer already copied.
- **Gap:** a node accepts a manifest from any holder; only the owner signature and version check protect it. Owner key rotation and revocation are unbuilt.
- **Gap:** no rate limits or size caps on requests yet.
- Pure-Python Ed25519 (used where `cryptography` is unavailable, e.g. iOS) is slower and not hardened against timing attacks; acceptable for the spike, not for production.

## Out of scope for v0.1
Anonymity, traffic analysis resistance, payments, proofs of storage, global moderation, malicious
AI agents, sandboxed third-party apps, private (encrypted) replication.

## Residual risks
- A trusted peer can still serve stale (older but validly signed) versions unless version checks are enforced by clients.
- A compromised owner key can sign malicious updates until revocation exists.
- Local network attackers can deny service.
