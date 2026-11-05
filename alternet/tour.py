"""`alternet tour`: a narrated, self-contained walk through what makes Alternet different.
Runs the real signing/verification code (site.py, crypto.py) between three in-memory-style stores in a temp
directory; it does not use the network, so it works anywhere with no setup."""
import os, shutil, sys, tempfile, time
from . import crypto, site as sitelib

B, D, G, R, C, X = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[36m", "\033[0m"

PAGES = {
    "index.md": "# My tiny site\n\n1. [about](about.md) - who I am\n",
    "about.md": "# About\n\nPublished from my own computer. No host, no account.\n",
}


def _say(text="", pause=0.0):
    print(text, flush=True)
    time.sleep(pause)


def _wait(fast, prompt="  (press Enter)"):
    if not fast and sys.stdin.isatty():
        input(D + prompt + X)


def _step(n, title, fast):
    _say("\n%s%s[%d] %s%s" % (B, C, n, title, X))


def _replicate(src, dst, sid, say):
    """What a node does on receiving a site: verify the signature, then verify every block, then store."""
    m = src.get_manifest(sid)
    body = sitelib.verify_manifest(m)
    say("    signature ok, owner %s..." % body["owner"][:12])
    n = 0
    for ids in body["files"].values():
        for h in ids:
            blk = src.get_block(h)
            if blk is None:
                raise ValueError("holder is missing block " + h[:8])
            sitelib.verify_block(h, blk)
            say("    block %s... %d bytes %sverified%s" % (h[:12], len(blk), G, X))
            dst.put_block(h, blk)
            n += 1
    dst.put_manifest(m)
    return body, n


def run(fast=False):
    tmp = tempfile.mkdtemp(prefix="alternet-tour-")
    pause = 0.0 if fast else 0.35
    say = lambda t="": _say(t, pause / 3)
    try:
        _say("%s%sALTERNET TOUR%s  %s(runs the real signing + verification code, no network needed)%s" % (B, C, X, D, X))
        _say("Three computers: %sAlice%s publishes, %sBob%s replicates, %sCarol%s only ever talks to Bob." % (B, X, B, X, B, X))
        _wait(fast)

        _step(1, "Alice publishes a site from her own machine", fast)
        pages = os.path.join(tmp, "pages")
        os.makedirs(pages)
        for name, text in PAGES.items():
            with open(os.path.join(pages, name), "w") as f:
                f.write(text)
        alice = sitelib.Store(os.path.join(tmp, "alice"))
        key = crypto.SigningKey.load_or_create(os.path.join(tmp, "alice.key"))
        m, blocks = sitelib.pack(pages, key, "tiny", 1)
        for h, b in blocks.items():
            alice.put_block(h, b)
        alice.put_manifest(m)
        sid = m["body"]["site"]
        say("    pages: %s" % ", ".join(sorted(m["body"]["files"])))
        say("    site id: %s%s%s   (derived from her public key + name)" % (B, sid, X))
        say("    signed with her private key; the private key never leaves her machine")
        _wait(fast)

        _step(2, "Bob copies it. He checks everything instead of trusting Alice or the wire", fast)
        bob = sitelib.Store(os.path.join(tmp, "bob"))
        body, n = _replicate(alice, bob, sid, say)
        say("    %sBob now holds a verified replica (%d blocks, version %d)%s" % (G, n, body["version"], X))
        _wait(fast)

        _step(3, "A tampered copy is rejected", fast)
        h = next(iter(blocks))
        evil = bytearray(blocks[h]); evil[0] ^= 0x01
        say("    an attacker flips one bit in block %s..." % h[:12])
        try:
            sitelib.verify_block(h, bytes(evil))
            say("    %sBUG: tampered block accepted%s" % (R, X))
            return 1
        except ValueError as e:
            say("    %sREJECTED%s: %s" % (R, X, e))
        forged = {"body": dict(m["body"], version=2), "sig": m["sig"]}
        try:
            sitelib.verify_manifest(forged)
            say("    %sBUG: forged manifest accepted%s" % (R, X))
            return 1
        except ValueError as e:
            say("    a forged manifest (version bumped, signature copied) is %sREJECTED%s: %s" % (R, X, e))
        _wait(fast)

        _step(4, "Alice's computer goes offline. The site does not", fast)
        shutil.rmtree(os.path.join(tmp, "alice"))
        say("    %sAlice's machine is gone.%s" % (D, X))
        carol = sitelib.Store(os.path.join(tmp, "carol"))
        body, n = _replicate(bob, carol, sid, say)
        say("    first line Carol sees: %r" % carol.read(sid, "index.md").decode().splitlines()[0])
        say("    %sCarol read the site from Bob's replica, fully verified against Alice's signature.%s" % (G, X))
        _wait(fast)

        _say("\n%sWhat you just saw%s" % (B, X))
        _say("  - no company, account, or rented server was involved at any step")
        _say("  - anyone can check a copy came from the owner, from any holder")
        _say("  - the site outlived its publisher's machine")
        _say("\nTry it for real:  %salternet bbs bbs%s  (after: alternet connect y-0-x.com:4242)" % (B, X))
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
