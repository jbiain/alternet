# 011 — LoRa carrier spike, and running more gateways (planned 2026-11-04)

## Why
Today everything reachable beyond one LAN rides on paid internet (the VPS relay, Wi-Fi, 4G). The pitch of
"no phone line, no internet bill" only becomes real once a carrier that costs nothing per month moves
announces and small site syncs between nodes. Reticulum already supports RF carriers, so this is a carrier
swap, not a protocol change (see 005).

## Spike: two LilyGo boards, no internet
- Hardware: 2x LilyGo LoRa boards (T3 or T-Beam; ESP32 + SX126x/SX127x), roughly $25-35 each, powered by
  USB for the spike. Pick the band for the region (868/915 MHz).
- Software: flash Reticulum's RNode firmware onto each board; the board then appears to the host as a
  standard Reticulum `RNodeInterface`. No custom protocol code on our side.
- Setup: each computer plugged into its own board. Add an `RNodeInterface` to the Reticulum config in place
  of `TCPClientInterface`; the Alternet home/config writer (`home.write_rns_config`) will need a small
  option for it. Run `alternet node` on both, publish `examples/bbs-menu` on one, `alternet read` it on the other.
- Pass criteria: the 8-page BBS site announces, fetches, and verifies on the second machine with internet
  disabled on both.
- Measure: achieved range in our environment, wall-clock time to fetch the whole site, behaviour at the edge
  of range (does fetch fail cleanly and resume), and whether announces stay under airtime limits.
- Out of scope: multi-hop mesh, antenna tuning, weatherproofing, HF/20m, phones as nodes.

## Open questions
- LoRa throughput is on the order of hundreds of bits/s to a few kbit/s: is a whole site fetch acceptable,
  or do we need smaller blocks / manifest-first fetching?
- `MAX_ANNOUNCED` and announce burst timing were tuned for TCP relays; airtime is far scarcer.
- Regional legal duty-cycle limits for the chosen band.

## More gateways (not just ours)
The protocol never depends on one server: sites are addressed by signed content, so any gateway shows the
same site. Ours (https://y-0-x.com/) is one door because nobody else has run one yet, a bootstrapping
problem rather than an architectural one. To make a second gateway easy:
1. Document the gateway recipe (systemd unit, Caddy, relay hint) in the README as "run your own".
2. Let each operator publish their own directory site; `/directory` and `/llms.txt` already work per gateway.
3. Later: a convention for gateways to list each other, so which one you use stops mattering.

Status: planned. The spike needs physical boards; nothing here is built yet.
