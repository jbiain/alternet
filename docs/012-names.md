# 012 - Names and ids: options and a recommendation (analysis, 2026-11-05)

## The problem
A site id is 32 hex characters. People cannot read, say aloud or remember it. We want readable names without
giving up the property that nobody can take your site or forge it.

## The constraint (Zooko's triangle)
A name cannot be all three of: human-readable, globally unique, and controlled by no central party.
Every system picks two and works around the third. Our site id is secure and decentralised but not readable.

## What exists today
- Petnames: local nicknames on one device. Secure and private; not shared.
- Shared signed directories: a site with a `names.json` page that others can subscribe to.
- The landing BBS lists sites that opted in with `--list`.

## Options considered
1. **Default subscribed directory.** `alternet start` subscribes you to our directory; anyone can run a rival.
   Easy and good for newcomers. Whoever runs the default becomes a soft naming authority; most people
   never change defaults.
2. **Domain-verified names.** A site claims a domain in its signed manifest; clients check
   `https://DOMAIN/.well-known/alternet.json` for the same owner key. `y-0-x.com` then names our site with no
   registry of ours. Reuses DNS (cheap, familiar, already global) but ties readable names to DNS and registrars.
3. **First-use pinning (like SSH known_hosts).** The first time a name resolves to an id, remember it. If a
   directory later returns a different id for that name, warn loudly. Closes the "directory swapped the
   site" attack without any new infrastructure.
4. **Short display names and prefixes.** Show `bbs.7436` (name + first 4 id characters) and accept any unique id
   prefix of 6+ characters. Makes ids bearable, not memorable. Prefixes are display and convenience only;
   they are not a security boundary (short prefixes can be brute-forced to collide).
5. **Pronounceable ids (word lists).** Encode the id as words. 4 words is about 44 bits: easy to say, but
   weak against collisions, so only fine as a display aid next to option 3.
6. **Blockchain or paid registry.** Gives readable, unique, decentralised names, at the cost of a chain, fees and
   speculation. Contradicts the "no bill" goal. Rejected.

## Recommendation
Combine 1, 3, 4 (and 2 later), in this order:
- Subscribe new users to a default directory (1) so `home`, `bbs` and friends just work.
- Pin on first use and warn on change (3): the security property that makes (1) acceptable.
- Show `name.xxxx` and accept unique prefixes (4) so ids stop being a wall of hex.
- Add domain-verified names (2) for operators who own a domain; it is optional and additive.
This keeps the protocol free of any registry while giving normal people names they can read.

## Status
Built (2026-11-05): `NAME@OWNERTAG` resolves a stored site (tag = first 6 characters of the owner key; a
32-character value after `@` is still a node address); `alternet sites` and the 3D world show names that way;
names learned from a shared directory are pinned on first use, and a later change is refused with an
explanation until you run `alternet name unpin NAME`. Not built: a default directory for new users,
domain-verified names, and resolving `NAME@OWNERTAG` for sites not yet stored locally.
