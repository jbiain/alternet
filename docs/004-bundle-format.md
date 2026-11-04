# 004 — Bundle Format (draft, carrier-independent)

Goal: one signed, content-addressed unit that can move over any carrier — LAN stream, hotspot,
USB/SD, later Bluetooth or LoRa — without change. All values here are provisional.

## Objects
- **Block**: a chunk of bytes (target ≤ 64 KiB; small enough to retry over slow links). Identified by its hash (e.g. BLAKE3 or SHA-256 multihash; to be fixed after the spike).
- **Page**: UTF-8 text or Markdown, stored as one or more blocks.
- **Manifest**: a document listing `path → [block ids]`, with:
  - `site_id` (derived from the owner public key + site name)
  - `version` (monotonic integer)
  - `created` timestamp
  - `owner` public key
  - `signature` over the canonical encoding of the above
- **Bundle**: a manifest plus any subset of its blocks, as a single file or stream.

## Rules
1. A reader must verify the signature and every block hash before storing or serving anything.
2. A newer `version` from the same owner replaces an older one; older versions are rejected after a newer one is seen.
3. Bundles may be partial; missing blocks can be requested from any peer or imported later.
4. Messages are small and independent so they survive links with ~200–500 byte payloads.
5. Encoding is a deterministic canonical form (e.g. CBOR or canonical JSON) so signatures are reproducible.

## Carriers (informative)
- Stream carrier: request manifest, then request missing block ids.
- File carrier: `.altbundle` file copied by hand.
- Future: Bluetooth/LoRa chunks carrying individual blocks.

## Open questions
- Hash and signature algorithm choices, to follow the foundation decision.
- Large-file chunking policy.
- Private (encrypted) sites.
