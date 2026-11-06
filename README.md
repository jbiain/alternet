# Alternet Core 0.1

A small command-line tool for publishing **signed, content-addressed text sites** and replicating
them between nodes, with no central server. Terminal-first: no browser, no HTTP.

**Live demo, no install needed:** https://y-0-x.com/ (public gateway and relay)

Status: prototype. Reticulum is used only as the network carrier; the signing, content addressing, store
and bundles (`alternet/site.py`) have no network dependency.

## What it does (and does not)

Does: sign a directory of `.txt`/`.md` pages; announce it; let other nodes fetch it over an encrypted
link, verify every block and the signature, store it, serve it onward, and keep it updated; export and
import a site as one file for USB/SD.

Does not (yet): encrypted private content, names (you use a 32-character site ID), a browser gateway, or reaching nodes behind NAT on
other networks. See "Limits" below.

## Install

Python 3.9 or newer.

```
cd core
python3 -m venv .venv && . .venv/bin/activate
pip install -e .                  # installs the `alternet` command and Reticulum (`rns`)
pip install cryptography          # optional: faster crypto; without it a pure-Python fallback is used
alternet --version
```

You can also run it without installing the command: `python -m alternet ...`.

## Quick start (one machine)

```
alternet init --no-auto                     # creates ~/.alternet with your owner key
alternet publish examples/sample-site --name alice
alternet sites                              # shows the 32-character site ID
alternet ls <id-prefix>                     # list pages
alternet read <id-prefix>                   # prints index.md (or the first page)
alternet read <id-prefix> about.txt
```

Publishing again with the same name makes version 2, 3, ... Use `--home DIR` (or `ALTERNET_HOME`) to
keep separate identities.

## Demo 1: everything on one machine (Proof 01 + Proof 03)

Runs three nodes and a fourth fresh reader, checks replication, update propagation, offline survival and
tamper rejection. About a minute.

```
python examples/three_nodes.py        # exit code 0 and "ALL STEPS PASSED" when it works
```

Steps it performs: A publishes and serves; B pins from A; C (connected only to B) reads; A publishes v2
and B updates itself; A is killed and a fresh node D still reads v2 from B; a corrupted bundle is rejected.

## Demo 2: two computers on one network

On computer A (the publisher):
```
alternet init --no-auto
alternet listen 4242
alternet publish examples/sample-site --name alice     # note the Site ID
alternet node                                          # leave running; allow the firewall prompt
```
On computer B (find A's address with `ipconfig getifaddr en0` on macOS or `hostname -I` on Linux):
```
alternet init --no-auto
alternet connect <A-address>:4242
alternet read <Site ID> --wait 20
```
B prints the page after verifying the signature and block hashes. To keep a replica, also run
`alternet pin <Site ID>` and `alternet node` on B. Stop A, and a third computer that connects to B can
still read the site.

On desktops you can drop `--no-auto` to try Reticulum's automatic LAN discovery (multicast), and skip
`connect`/`listen`. It does not work on iOS and may not work on networks that isolate clients.

## Demo 3: an iPhone (a-Shell)

Verified on 2026-11-04 with this `alternet` CLI (Mac + iPhone, same Wi-Fi: init, connect, read, sites, read --offline). The older spike also ran on the iPhone's hotspot. Install **a-Shell**
(free, App Store). Install Reticulum without dependencies (`--no-deps`). On the tested phone a-Shell already
provided `cryptography` (the tool reported `Crypto backend: cryptography`); if yours does not, the
pure-Python fallback is used automatically (tested on the Mac, not on a phone).
```
pip install --no-deps rns
# copy the core/ folder to the phone, for example:
#   on the Mac:   cd core && python3 -m http.server 8000     (same Wi-Fi)
#   in a-Shell:   curl -O http://<mac-address>:8000/core.tgz && tar xzf core.tgz
#   (create it first with: COPYFILE_DISABLE=1 tar --format ustar -czf core.tgz alternet examples)
python -m alternet init --no-auto --standalone
python -m alternet connect <mac-address>:4242
python -m alternet read <Site ID> --wait 20
```
Notes: a-Shell cannot write above `Documents`, so Alternet automatically stores its data in `~/Documents/.alternet` there (or pass `--home DIR`). Run commands one per line; a-Shell does not handle `&&`. Auto-discovery does not work on iOS, so use `connect` with the other device's address. To make the
phone a replica, run `python -m alternet pin <Site ID>` then `python -m alternet listen 4243` and
`python -m alternet node`, and keep a-Shell open in the foreground (iOS suspends it in the background).

## Demo 4: across the internet through a relay

Two devices on different networks (for example a home computer and a phone on mobile data) cannot
connect directly because home routers block incoming connections. Both connect OUT to a relay: a node
on a machine with a public address (a small cloud VPS works) that forwards traffic. The relay never needs
to be trusted with content: every block and manifest is verified by the reader.

Set up a relay (Ubuntu 24.04 example, as root on the server; port 4242 is arbitrary):
```
apt-get install -y python3-venv
useradd --system --create-home --home-dir /var/lib/alternet --shell /usr/sbin/nologin alternet
python3 -m venv /opt/alternet/venv && /opt/alternet/venv/bin/pip install /path/to/core
runuser -u alternet -- env ALTERNET_HOME=/var/lib/alternet /opt/alternet/venv/bin/alternet init --no-auto --standalone --relay
runuser -u alternet -- env ALTERNET_HOME=/var/lib/alternet /opt/alternet/venv/bin/alternet listen 4242
# run `alternet node` under systemd (User=alternet, Environment=ALTERNET_HOME=/var/lib/alternet, Restart=always)
ufw allow 22/tcp && ufw allow 4242/tcp && ufw enable
```
Publisher (any network):
```
alternet connect RELAY_IP:4242
alternet publish examples/sample-site --name alice     # prints "Share as: SITEID@NODEADDRESS"
alternet node
```
Reader (any other network):
```
alternet connect RELAY_IP:4242
alternet read SITEID@NODEADDRESS --wait 60
```
Use the full `SITEID@NODEADDRESS` when you can: the address makes the reader ask the network for a path to the holder
(`alternet address` prints it), which works even through relays that rate-limit announcements. Without it, discovery relies on the holder's announcements (see Limits). Verified 2026-11-04: Mac publisher and an iPhone reader through a VPS relay.
Warning: without the allowlist (not built yet) anyone who finds the relay's address can connect to it.

## Demo 5: private sites (trusted peers)

By default a published site is public: anyone who can reach your node can read it. Publish with
`--private` and only peers you trust can fetch it. The flag is signed into the manifest, so replicas
honor it too.

```
# on the reader (B): find your peer id
alternet address                         # prints "node address" and "peer id"
# on the publisher (A): publish privately and trust B's peer id
alternet publish examples/private-site --name secret --private
alternet trust <B's peer id>             # takes effect immediately, no restart
alternet node
# on B
alternet read <site-id>@<A's node address>
```
Peers you did not trust get the same answer as "not found", even if they know the block hashes.
`alternet untrust <peer id>` revokes access; `alternet trusted` lists peers. Private sites are never
announced, so readers need the full `SITEID@NODEADDRESS`.
Verified by `python examples/private_site.py` (trusted peer reads, untrusted peer refused, direct block
requests refused, revocation works).

What this does NOT do: private content is **not encrypted at rest** and replicas hold it in plain text.
Trusting a peer lets that node read, copy and re-serve what it fetched, subject to its own settings.
Identity is per node (not per person), a trusted node's key theft gives access, and a reader reveals its
peer id to every holder it contacts. Treat it as access control between machines you choose, not as
confidentiality against a hostile host. The link itself is encrypted end to end, so a relay cannot read it.

## Demo 6: moving a site by USB stick (no network)

```
alternet export <Site ID> /Volumes/USB/alice.altbundle      # on computer A
alternet import /Volumes/USB/alice.altbundle                # on computer B
alternet read <Site ID> --offline
```
Import verifies the signature and every block first and stores nothing if anything is wrong.

## Demo 7: terminal apps and apps as sites

A site that contains an `app.json` is an app. Its files are signed like any site, and the host or your own
machine runs it in an OS sandbox (bubblewrap on Linux, Seatbelt on macOS): read-only system, private `/tmp`,
no network unless the app asks and the host or you allow named hosts. Design: `docs/014-apps-as-sites.md`;
security model: `docs/013-security.md`.

```
# host: one address that serves apps (each visitor gets their own sandboxed copy)
alternet app-serve --name chat --access public python3 app4.py
# visitor: open it from anywhere (Ctrl-] disconnects). Each app has its own address (shown at start);
# the host's menu address lists them all
alternet open ADDRESS                 # or SITE@ADDRESS, or a bare SITE id
# run an app site on your own machine, sandboxed
alternet run SITE
```
Visitors see what the app will do (runtime, network hosts, storage) and approve it before it runs. Secrets such
as an API key are typed by the visitor, held in memory only and never stored by the host. Per-app storage is
kept on the visitor's side (up to 8 MB). Terminal output is filtered so an app cannot use escape sequences to
read your clipboard or query your terminal.

A browser works too: open `/terminal` on a gateway (for example https://y-0-x.com/terminal), paste an app address, and the
terminal runs in the page. On a public gateway the operator can see your session; run `alternet gateway` locally for private use.

## Demo 8: sharing connectivity and keeping storage in check

```
alternet relay                        # forward traffic for others (share your WiFi/connection)
alternet relays [--add HOST:PORT]     # list known relays; `start` joins up to 3 of them
alternet gc --limit 500               # drop least-recently-used sites until under 500 MB
```
Pages can embed images (`![](logo.png)`) and simple forms (`:input`, `:check`, `:calc`); form values stay on
your machine. Sites you have read are cached, so they work offline (`sites` marks each as offline-ok or PARTIAL).

## Commands

| Command | Purpose |
|---|---|
| `init [--no-auto] [--standalone] [--relay]` | create your home, owner key and settings |
| `publish DIR --name NAME [--version N]` | pack and sign a site; version defaults to previous + 1 |
| `sites` / `ls SITE` | list local sites / list a site's pages |
| `read SITE [PATH] [--wait S] [--refresh] [--offline]` | print a page; fetch from the network if not stored |
| `pin SITE [--remove]` | keep a site replicated and updated while your node runs |
| `node [--interval S]` | run your node: announce and serve your sites, apply pins |
| `connect HOST:PORT` / `listen PORT` | add a peer / accept TCP connections |
| `config [--auto on/off] [--relay on/off] [--clear]` | show or change network settings |
| `export SITE FILE` / `import FILE` | `.altbundle` for USB/SD |
| `publish ... --private` | serve the site only to trusted peers |
| `trust PEERID` / `untrust PEERID` / `trusted` | manage who may read your private sites |
| `address` | show your node address and peer id |
| `id` | show your owner public key |
| `app-serve [--name N] [--access public|trusted] [--net HOSTS] CMD...` | serve a sandboxed terminal app on its own address |
| `open ADDR[/APP]` / `SITE@ADDR` / `SITE` | connect to a hosted app |
| `run SITE` | run an app site locally in an OS sandbox |
| `relay` / `relays [--add]` | act as a relay / list known relays |
| `gc --limit MB` | evict least-recently-used sites |

Network changes take effect when you restart `alternet node`. Site arguments accept a unique ID prefix
for local sites; use the full 32 characters to fetch a new site.

## Files

Under `~/.alternet` (or `--home`): `owner.key` (your signing key, mode 0600; **back it up**, losing it means
you can no longer update your sites), `settings.json`, `pins.json`, `store/` (blocks and manifests),
`reticulum/` (generated config; do not edit, use `connect`, `listen`, `config`), `node.identity`.

## Tests

```
python -m unittest tests.test_site          # fast: signing, tampering, bundles, path tricks, crypto interop
python -m unittest tests.test_network       # about 4 minutes: three_nodes.py, private_site.py, relay_discovery.py
```

## Limits and known issues (v0.1)

- **Access control is coarse.** Public sites are readable by anyone who can reach your node. Private sites are limited to trusted peers (Demo 5) but are not encrypted at rest.
- **NAT:** direct connections need a reachable address. Across networks use a relay (Demo 4); hole punching is future work.
- **Relays you do not control may stop forwarding your announcements.** Reticulum relays rate-limit announces per destination (default 1 per hour with 5 spare) and then block that node for about an hour. Alternet nodes announce politely (short burst at start, on changes, then every 30 s by default) and relays set up with `init --relay` relax the limit, but a stock Reticulum relay may still block you. `SITEID@NODEADDRESS` does not depend on announcements, so use it with third-party relays.
- **No names.** Sites are identified by a 32-character hex ID. There is no discovery or search beyond what connected peers announce.
- A node announces at most 8 sites. Pins fetch updates only while `alternet node` runs.
- Old blocks are not garbage-collected after you publish a new version (`alternet gc` evicts whole sites by last use).
- **Apps:** sandboxing needs bubblewrap on Linux (Ubuntu 24.04 also needs an AppArmor `userns` profile) or macOS Seatbelt; Windows is refused. No per-session CPU/memory limits yet. Apps with shared live state (chat rooms, games) are not solved.
- Several nodes on one machine: use `init --standalone` and different `--home` directories, as the demos do. In the default shared mode, two different homes on one machine confuse Reticulum's local instance.
- Phones: iOS has no auto-discovery and suspends apps in the background; treat phones as clients and occasional peers.
- Pure-Python Ed25519 (used when `cryptography` is missing) is slower and not hardened against timing attacks.
- The key file is not passphrase-protected; there is no key rotation or revocation yet.

## Browser gateway: zero-install reading, like visiting a website

`alternet gateway` is the same CLI, serving sites to any ordinary browser - no app, no account. Unlike the demo
below, it also fetches and verifies any public site id on demand over the network, not only ones already stored
locally - a real gate to the whole network. Private sites never appear in a listing and are refused even by
direct link, because the gateway has no peer identity to check trust against (same as a browser visitor).

**Try the live one, no install at all:** https://y-0-x.com/ - type any public site id, or use the
form to open one you don't have locally.

**Run your own:**

```
alternet gateway --bind 0.0.0.0 --port 4280
```

Open `http://<this computer's LAN IP>:4280/` in a phone's normal browser, on the same Wi-Fi. Stop with Ctrl-C;
nothing is left listening afterwards.

**Installing the `alternet` command itself** (to publish, replicate, or run `bbs`/`node`) is a different tier -
reading is zero-install, taking part needs the CLI, same as any peer-to-peer tool:

```
curl -fsSL https://y-0-x.com/install.sh | sh
```

## Licence note

Alternet's own code is licensed under **Apache-2.0** (see `LICENSE`). Reticulum is **not** part of this
repository and is not vendored: it is installed separately from PyPI (`pip install rns`) and is distributed
under its own "Reticulum License" (MIT plus a no-harm clause and a no-AI/ML-training clause, not
OSI-approved). By installing it you accept that licence. Alternet keeps its signing, storage and bundle code
independent of the carrier (`site.py`, `crypto.py`, `home.py`), so another carrier can replace it. See
`docs/006-licence-decision.md`. This is not legal advice.

## Petnames

Site ids are unreadable, so you can give them private local labels. They live in `names.json` in your home
and are never sent to anyone; the site id remains the identity.

```
alternet name add blog 3fa9c1...32hex...@NODEADDRESS
alternet name list
alternet read blog
alternet name rm blog
```
