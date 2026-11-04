# 002 — Problem Statement (draft, one page)

## The problem

Taking part in the network means renting space on someone else's platform. Publishing a page, running
a mailbox, hosting a chat community or serving a local LLM all lean on third parties: DNS registrars,
hosting companies, cloud providers, app stores, certificate authorities. Those add cost, rules,
accounts and points of control. Meanwhile ordinary computers sit idle in homes, and a group of
people in the same room, street or village often cannot share anything without going through a
data centre on another continent.

HTTP and the web assume always-on servers, DNS names and a browser. They are poor fit for a plain
terminal, for intermittent machines, and for places with no uplink.

## What Alternet would let someone do

- Publish a text site from a laptop and have friends or neighbours read it with no hosting account.
- Keep that site available when the laptop is off, because a trusted peer holds a verified copy.
- Move content between machines with no network at all, using a USB stick.
- Do all of this from a terminal, BBS-style, with no browser.

## Proof points for v0.1

- **Proof 01:** two or three machines with no internet publish, discover and read a signed text site.
- **Proof 03:** the site stays readable from another node after the original host disappears.

## Status (2026-11-04): what has been shown
Spike on Reticulum (spike/reticulum/RESULTS.md), Mac + iPhone on one Wi-Fi and on an iPhone hotspot:
- Proof 01 (local part): a signed text site was fetched, verified and read between two real devices.
- Proof 03: with the publisher stopped, the iPhone served its verified copy to a fresh node.
- Limits found: iOS cannot auto-discover peers (needs a typed address), only serves in the foreground,
  and has no `cryptography` package (pure-Python crypto fallback works). Truly no-internet was not
  tested (the phone's hotspot needs mobile data on). Treat phones as clients and occasional peers.

## Candidate first audiences (to decide)

| Audience | Pain today | Pros | Cons |
|---|---|---|---|
| Self-hosters / hobbyists | Rely on cloud, DNS, dynamic IP | Can install nodes, give feedback | Many already use Tailscale, Syncthing |
| Off-grid / mesh communities | No reliable uplink | Real need for store-and-forward | Radio links require non-IP transports |
| Retro / BBS / terminal fans | Nostalgia, few modern options | Small, enthusiastic, tolerant of rough edges | Limited reach |

Recommendation: start with self-hosters and BBS/terminal enthusiasts for a quick feedback loop,
while keeping the bundle format low-bandwidth friendly so off-grid use stays possible. **Decision pending.**

## What this is not

Not a replacement for the internet, not an anonymity tool, not a cryptocurrency, not a social network.

## Risks

- Cold start: a network with no content gives no reason to join.
- Home nodes sleep, sit behind NAT, and are not reliable hosts.
- Hosting other people's content creates legal and abuse risk.
