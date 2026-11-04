# 007 — Names and first audience (proposal)

## Names
Today a site is `SITEID` (hash of owner key + site name) and optionally `@NODEADDRESS`. That is unambiguous but unreadable.
Proposed layers, each optional, built in this order:
1. **Petnames (local).** `alternet name add blog 3fa9…` — a private alias in your own `names.json`. No network, no trust problem. Cheap; do first.
2. **Signed name claims (owner-published).** An owner publishes a signed record "my key calls this site `alice/blog`". Readers
   accept it only if they already trust that key (key pinned, or introduced by a trusted peer). Gives readable names inside a trust circle.
3. **Global names (not planned).** Needs consensus, a registrar or a blockchain: all contradict the "no central party" goal. Defer until real demand.
Rules: the key is the identity; a name is only ever a pointer to it. Never show a claimed name without the key fingerprint nearby. Use `.alt` (RFC 9476) if DNS-style naming is ever needed.

## First audience
| Audience | Fit now |
|---|---|
| Self-hosters / terminal users | Best: install Python, tolerate rough edges, already want to avoid cloud |
| BBS / retro fans | Good for feedback and content, small reach |
| Off-grid / mesh communities | Strongest need, but needs radio carriers we have not built |
**Recommendation:** self-hosters and terminal/BBS enthusiasts first. Concrete first use case: a small group (5-20 people) sharing a
text site/zine that stays readable when any one member's machine is off. Success test: three real people, none of them us,
install it and read each other's sites for a week.
Needs before inviting anyone: a one-command install, a stable public relay (exists), petnames, and the licence decision (006).

## Name collisions (two people pick the same name)
Not a bug: a name is only a label, the key is the identity. `blog` by Ana and `blog` by Luis are different sites with different
site ids. A search for `blog` returns every match with owner fingerprint, and the reader picks and gives it a petname.
Readable discovery without a central registry: **directories** — ordinary signed sites listing `name -> site id`. Anyone can publish one;
you subscribe to the ones you trust (the BBS "list of boards" model). Squatting just means a bad directory you ignore.
**Blockchain:** gives first-come global uniqueness (ENS, Namecoin precedent) but adds fees, squatting, a consensus dependency and a lot of
scope, against the "ordinary computers, no third parties" goal. Deferred; if ever wanted, it becomes one more resolver
behind the same name interface, not the foundation.

## Built (2026-11-04)
Signed directories are real, not just proposed: a directory is an ordinary published site whose `names.json`
page maps `name -> "SITEID"` or `"SITEID@ADDR"`. `alternet directory add SITE[@ADDR]` subscribes; names then
resolve anywhere a site ref is accepted (`read`, `ls`, `pin`, `export`, `bbs`), the same as a local petname, but
shared - verified end to end: a node that only subscribed to the live directory on the VPS resolved `alternet
read bbs` with zero manual mapping. Also built: an opt-in `--list` flag on `publish` (signed into the manifest,
off by default) and a `/directory` page on the gateway that only shows sites whose owner asked to be listed -
"nothing is surfaced without being asked," by design, not just by omission.

## Decision status
Audience: **accepted** (self-hosters and terminal/BBS fans first). Names: petnames first, then directories; blockchain deferred.


## Pending / revisit later (2026-11-04)
- Installer prompt for `--list`: right now it's a flag the publisher adds by hand to `publish`; consider
  making the install/publish flow ask interactively instead of relying on people knowing the flag exists.
- Search engine tiers (see conversation log / session notes): current build is tier 1 (one relay's own
  observed + opted-in sites, via `/directory`). Tier 2 (a dedicated multi-relay crawler + keyword index,
  SQLite FTS5-sized effort, days not weeks) is the natural next step once there is more than a couple of
  real sites worth indexing. Tier 3 (gossip/DHT-based discovery across nodes) is deliberately deferred -
  bigger architectural change, probably unnecessary at current scale.
