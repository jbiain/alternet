# 014 — Apps as sites (design, not built)

Status: steps 1-6 built (`appspec.py`, `apphost.py`, `localrun.py`). Local execution is tested on macOS (Seatbelt);
the Linux path reuses the hosted bubblewrap sandbox but has not been run locally yet. Windows is refused (no sandbox).

## Idea
A site is pages plus, optionally, an app. Both are the same signed, content-addressed, replicated object,
under the same address. Opening an address shows its pages, or runs its app.

This removes the usual web split between "the page" and "the backend you must keep alive": the app's code is
replicated like any page, so any node can host it, and the user's data lives with the user.

## The app file
A site that contains `app.json` is an app site. The file is an ordinary site file, so the existing manifest
signature already covers it (and the code it points to). Draft:

```json
{
  "app": 1,
  "title": "Codex",
  "run": ["codex", "--dangerously-bypass-approvals-and-sandbox"],
  "runtime": "native",
  "needs": {
    "secrets": ["OPENAI_API_KEY"],
    "net": ["api.openai.com", ".openai.com"],
    "storage_mb": 50,
    "seconds": 3600
  }
}
```
- `run` / `runtime`: what to start inside the sandbox. `runtime` names a runtime the *host* provides
  (`python3`, `node`, `native`). Hosts decide which runtimes they offer; the site never ships a runtime.
- `needs` is the complete list of what the sandbox may get. Anything not listed is denied (013 defaults).

## Who runs it
1. **A host** that holds the site and serves apps (today: `app-serve`). The host chooses which sites to host.
   Because the bundle replicates, several hosts can serve the same app address; the client picks any reachable one.
2. **Your own machine**, locally, in the same sandbox, after a prompt. (Later; needs sandboxes on macOS/Windows.)

The signature proves who published the app and that the code is unmodified. It does not prove the code is safe:
that is the sandbox's and the permission prompt's job.

## Permissions (replaces special cases like "bring your own key")
When a client opens an app it shows the `needs` and asks once, remembering the choice per site and per host:

    codex@a1b2c3 wants: your OPENAI_API_KEY, network to api.openai.com, 50 MB storage. Allow? [y/N]

- **secrets**: values come from the visitor (typed, hidden, or from the client's environment), travel over the
  encrypted link, exist only in that session's environment on the host, are never written to disk.
  Trust consequence: the host process handles them. Use capped keys; prefer hosts you trust.
- **net**: becomes the egress allowlist proxy (`netproxy.py`). No entry, no network.
- **storage**: see below. **seconds**: session limit, bounded by the host's own cap.
Hosts may enforce stricter limits than an app asks for and may refuse an app entirely.

## Data belongs to the user
Hosted compute is stateless by default. Persistent state is stored client-side: the client keeps a per-site,
per-user store and mounts it into the session (synced up/down over the same link). The host never keeps
user data after the session. This is the answer to "the backend": there is none to run, only compute.

## What it does not solve
- **Shared live state** (chat rooms, multiplayer): needs a sync layer (CRDTs) or a host that stays up. Out of scope for v1.
- **Host sees your input.** Same as any hosted app. Local execution is the escape.
- **Who pays for compute.** Nothing in the protocol pays hosts. Volunteer and self-hosted at first.
- **Discovery of hosts.** A site id says what to run, not who runs it: needs an announce of "I serve app X"
  (extend the existing site announce) or a directory.

## Build order
1. `app.json` schema and validation, plus `alternet publish` support (check `needs` at publish time).
2. Host: serve any stored app site, not just entries in `apps.json`; keep `apps.json` as the host's policy
   (which sites, which runtimes, caps).
3. Client: `alternet open SITE` resolves names, finds a host, shows the permission prompt.
4. Secrets over the link (hidden prompt, memory-only on host). Codex becomes the first real app site.
5. Client-side per-site storage.
6. Local execution (Linux first).
