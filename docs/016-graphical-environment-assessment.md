# 016: Assessment of the "native graphical environment" proposal (v2)

Status: assessment only. Nothing in the repository was changed for it. Facts marked (verify) were not checked.

## What the proposal asks for
A Rust + Slint pixel environment that runs without a desktop (Linux DRM/KMS), also on macOS, QEMU and headless
servers, with a damage-based remote display protocol (RFB/VNC first) reached through SSH port forwarding.

## Assessment
| Question | Finding |
|---|---|
| Fit with the current design | Weak. Alternet is terminal-first: the hosted apps (`app4`, Codex, `mc`, the room) all draw into a terminal. A pixel shell needs a terminal-emulator widget before it can show any of them. |
| Size | Very large: toolkit app, headless renderer, remote protocol, console backend, three platforms. Years of work, for a project with no users yet. |
| Already covered more cheaply | The browser gateway runs on every platform without install, works headless and remotely, and needs no pixel protocol. The terminal client already draws images and forms. |
| Rust + Slint | Adds a second language and a boundary to the Python core before anything is visible. Slint's licence options (GPL / commercial / royalty-free tiers) must be checked against docs/006 (verify). Maturity of its Linux console backend: unchecked (verify). |
| Remote display | Building or embedding RFB/VNC is a product of its own. Browsers already provide a remote viewer. |
| Python core integration | The core has no stable API today (CLI plus internal modules). Any frontend in another language first needs a local IPC layer; do not parse CLI output. |
| Security | The proposal's cautions are right and match docs/013: untrusted content, separate trust decisions for display and for running code. A new remote-session surface would need its own authentication and isolation. |

## Recommendation
1. Do not start the Rust/Slint/KMS programme now.
2. Make the browser the first graphical front end (next section).
3. If native pixels are still wanted, do a Python spike (an off-screen buffer, an SDL window, a changed-region tracker).
   It answers "is this worth it" in days. The best justification would be a kiosk or appliance (a small computer that
   boots into Alternet), which the browser cannot serve.
4. Revisit Rust, Slint and a custom remote protocol only if the spike shows a clear need.

## Decision gates
- Gate A (before any native work): the browser front end exists and real users still ask for things it cannot do.
- Gate B (before Rust/Slint): licence check passes, Linux console backend verified on the target hardware, and a
  spike shows the Python approach is too slow or too limited.
- Gate C (before a custom remote protocol): measured comparison against VNC/RFB and against the browser approach.

## The browser as the front end
The existing gateway (`alternet gateway`) turns sites into web pages, read-only. Two additions make the browser a
full front end.
1. **A terminal in the page.** A terminal emulator running in the page (xterm.js is the usual one; MIT licence, verify)
   connected by WebSocket to the gateway, which runs the same client as `alternet open`. Every hosted app (chat,
   Codex, `mc`, the room) then works in a browser tab with no install. Pages with forms and images render as real
   HTML next to it. This is the "console as the main screen" idea, using an in-page terminal rather than the browser's
   developer console, which is hidden, awkward and not meant for this.
2. **Richer pages.** Forms, images and the calculator already exist in the page format; the gateway can render them as
   native controls.

Trust model, which must be stated plainly to users:
- On a **public gateway**, the gateway operator sees what you type and can read your app sessions. Fine for public
  apps, not for secrets or private rooms. Each web visitor needs an ephemeral identity of their own, not the gateway's,
  or "trusted" apps and one-session-per-identity rules would treat everyone as the gateway.
- On a **gateway you run yourself** (`alternet gateway` on localhost), your keys and data stay on your machine; the
  browser is only the screen. This is the mode to recommend for anything private.
- Abuse limits are needed on a public gateway: sessions per address, idle timeout, bandwidth.

## What a native spike would measure (if gate A passes)
Cold start, idle CPU, memory, bytes sent for a static page, a scroll and an animation, reconnect time, and comparison
against the browser approach and against VNC.
