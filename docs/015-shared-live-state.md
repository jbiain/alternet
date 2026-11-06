# 015: Shared live state (collaborative apps)

Status: design, nothing built yet.

## Problem
Each visitor to a hosted app gets an isolated sandbox. That is right for security, but it means apps cannot be
collaborative: a chat room, a board, a shared document or a game needs state that several visitors see and change.

## Two kinds of sharing, two mechanisms

### 1. Live sharing on one host (small, build first)
Visitors of the same app on the same host share one host-side directory, `/work/shared`, in addition to their private
`/work`. Apps coordinate through files (append-only logs, small databases, lock files), which is how most simple
multi-user terminal programs already work.
- Host policy per app: `shared: true`, `shared_mb` (quota, default 16), enforced by a size check and a read-only
  remount when over quota.
- Public apps: visitors can read and write each other's data in `/work/shared`. The app must treat it as untrusted input.
  Apps that need identity get the visitor's peer id in `ALTERNET_PEER` (host-verified, from the Reticulum link).
- Optional later: a shared session (several visitors attach to one pty, like tmux) for pair-working and games.

### 2. Shared state across hosts and offline (later)
For data that must outlive one host: a signed, append-only log per room (a feed). Each entry is signed by its author,
carries the hash of the previous entry it saw, and is content-addressed, so it replicates like any Alternet block.
Hosts and visitors merge feeds by union; ordering uses the hash links plus a timestamp tiebreak. This is a
simple CRDT (a grow-only set of signed entries), no consensus needed. Chat, boards and comments fit it; games with strict
turn order do not, and stay on a single host.

## Build order
1. `shared`/`shared_mb`/`ALTERNET_PEER` in the host, with tests (quota, isolation between different apps).
2. A demo chat room app using `/work/shared`, deployed on the VPS.
3. Shared session attach (optional).
4. Signed feeds: format in docs/004 style, `alternet feed` commands, sync through the existing block transfer.

## Risks
- A public shared directory can be filled or vandalised: quota and per-visitor write limits, and apps validate input.
- Feeds grow without bound: needs pruning and a size limit per feed.
- No access control inside a shared directory beyond host policy: trusted-only apps are the safe default for private rooms.
