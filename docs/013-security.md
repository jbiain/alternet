# 013 — Security model

Plain statement of what Alternet protects, what it does not, and what each action risks. It extends
[003](003-threat-model.md). It makes no claim of being unbreakable: it says where the lines are.

## The three questions
1. **Who published this?** Every site is signed by its owner key and addressed by a hash of that key.
2. **Was it changed?** Every block is verified against its content hash; replicas verify before serving.
3. **Can it hurt me when I open it?** Reading a site runs no code. Opening an app runs code on the *host's*
   machine, not yours (see below).

Signatures answer 1 and 2. They say nothing about whether a publisher is honest or an app is harmless.
That is question 3, and it is handled by sandboxing and by choosing who you trust.

## What each action risks
| You do | Runs code? | Worst case for you |
|---|---|---|
| Read a site / the BBS | No | Misleading text. Content is verified; names are pinned on first use. |
| `alternet open ADDR` (hosted app) | On the host | The app shows you text. Your client filters escape sequences that could read your screen, clipboard or keyboard state (`OutputFilter`). |
| Host an app (`app-serve`) | On your machine | A hostile visitor tries to escape the sandbox or exhaust resources. Mitigations below. |
| Run someone's code locally | On your machine | Not built. When built: off by default, explicit prompt, sandbox, signature check. |

## Hosting apps: defaults
- **The client never chooses what runs.** Only commands in the host's `apps.json` (or on the `app-serve`
  command line) are started.
- **Sandbox by default.** Each session runs in bubblewrap: read-only system directories, private `/tmp`,
  a private writable scratch directory (deleted on exit), no network unless the app sets `net: true`, no
  host environment variables, a new session and PID namespace, killed with the host process.
  `app-serve` refuses to start without a working sandbox unless you pass `--no-sandbox`, which says so loudly.
- **One private copy per connection.** Visitors cannot see each other. Nothing persists between visits.
- **Per-app access.** `access: public` (anyone) or `access: trusted` (only identities you added with
  `alternet trust`). Trusted apps authenticate the visitor's node identity over the encrypted link.
- **Limits.** Maximum simultaneous sessions, a wall-clock time limit per session, file-size limit, no core dumps.
- **Run the host as an unprivileged user** that owns nothing else, with systemd hardening
  (`NoNewPrivileges`, `ProtectSystem`, memory and task caps). The sandbox is a second wall, not the only one.

## Known limits (honest list)
- A sandbox reduces risk; it is not a proof. Kernel bugs exist. Keep the host patched and isolated.
- An app can still lie to or phish a visitor in text. Signatures prove who, not whether to believe them.
- Apps that need the network (`net: true`, e.g. an AI agent) can reach anything the host can reach.
  Give them a capped, revocable API key and prefer `access: trusted`.
- Secrets in `apps.json` `env` are readable by the host user. Keep that file `0600`.
- CPU and memory limits are coarse (rlimits and systemd caps, not per-session cgroups yet).
- Ubuntu 24.04 restricts unprivileged user namespaces; bubblewrap needs an AppArmor profile allowing
  `userns` (see below). Containers or microVMs are the next step if strangers can publish apps.

## Ubuntu 24.04 note
`/etc/apparmor.d/bwrap`:
```
abi <abi/4.0>,
include <tunables/global>
profile bwrap /usr/bin/bwrap flags=(unconfined) {
  userns,
  include if exists <local/bwrap>
}
```
then `apparmor_parser -r /etc/apparmor.d/bwrap`.

## Before inviting the public
Independent review of the crypto use and the sandbox, a published list of what was and was not reviewed,
and a way to report problems privately.
