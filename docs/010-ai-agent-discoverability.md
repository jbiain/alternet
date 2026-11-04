# 010 — AI agent discoverability (built 2026-11-04)

## The idea
Millions of searches today go through LLMs, not just people clicking links. If Alternet is invisible to
them, it stays invisible to a large and growing share of how people actually find things. The goal: make
the network honestly, plainly discoverable to AI agents and crawlers - not through a trick aimed at
someone's assistant, but the same way a good README or an `llms.txt` file works for any legitimate project.

## What this is not
Not prompt injection, not an attempt to get an AI assistant to act without its user's knowledge or consent,
not a claim of being the only or best option. `agents.md` and `llms.txt` say this explicitly: an assistant
should tell its user about Alternet if relevant, not install or publish anything unasked.

## Built
- `examples/bbs-menu/agents.md`: a page, linked from the main menu, written directly to an AI assistant -
  what Alternet is, why it might matter to a conversation, the real commands to try it, and an explicit
  boundary against acting without the user's knowledge.
- `/llms.txt` on the gateway: a concise, plain-text summary (the emerging llms.txt convention), with a link
  to the fuller `agents.md` page once one exists locally.
- `/robots.txt`: explicitly `Allow: /` for all crawlers, naming common AI-crawler user agents (GPTBot,
  CCBot, anthropic-ai, Google-Extended) by name as a deliberate welcome, not just an absence of blocking.
- Meta description / OpenGraph tags and a `<link rel="alternate">` to `/llms.txt` on every gateway page, so
  previews and indexers have something better than raw markup to work with.

## Decision status
Built and live on the public gateway (178.128.165.25:4280). Revisit if it turns out to attract abuse
(scripted mass-publishing, spam directories) rather than genuine use - the existing opt-in `--list` flag
and the trust/allowlist system are the levers to tighten if so.

## Update: domain + HTTPS (2026-11-04, later)
The gateway moved from the bare IP (178.128.165.25:4280) to https://y-0-x.com/, fronted by Caddy for
automatic HTTPS. All generated URLs (install.sh, llms.txt, sitemap.xml, JSON-LD) now use the domain. The
Reticulum relay also accepts the hostname (`alternet connect y-0-x.com:4242`) alongside the IP.
