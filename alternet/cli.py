"""alternet command-line interface."""
import argparse, json, os, sys
from . import __version__, site as sitelib, crypto
from .home import Home


def die(msg, code=1):
    print("alternet: " + msg, file=sys.stderr)
    sys.exit(code)


def _directory_lookup(home, name):
    """Check subscribed directory sites' names.json for `name`. Only reads what's already stored locally -
    a directory updates when you re-pin/re-fetch it, same as any other site; this never fetches on its own."""
    store = home.store()
    for ref in home.directories():
        dsid, _, _ = ref.partition("@")
        dsid = store.resolve(dsid) or dsid
        info = store.info(dsid)
        if not info or "names.json" not in info.get("files", {}):
            continue
        try:
            import json
            names = json.loads(store.read(dsid, "names.json").decode("utf-8"))
        except Exception:
            continue
        if isinstance(names, dict) and name in names:
            return names[name]
    return None


def _expand(home, ref):
    """Replace a name by the site reference it stands for: local petname first, then any subscribed
    directory site's names.json (see `alternet directory`). Only the part before any @ADDRESS is a name."""
    name, at, addr = ref.partition("@")
    if not home.exists():
        return ref
    target = home.names().get(name.lower()) or _directory_lookup(home, name.lower())
    if not target:
        return ref
    return target if not at else target.partition("@")[0] + "@" + addr


def _site(home, ref):
    ref = _expand(home, ref)
    store = home.store()
    try:
        sid = store.resolve(ref)
    except ValueError as e:
        die(str(e))
    return store, sid


def cmd_init(a, home):
    s = home.init(auto=(False if a.no_auto else None), standalone=(True if a.standalone else None),
                  relay=(True if a.relay else None))
    key = home.key()
    print("Alternet home:", home.path)
    print("Owner public key:", key.public_bytes().hex())
    print("Crypto backend:", crypto.BACKEND)
    print("Next: `alternet publish <dir> --name <name>`, then `alternet node`.")


def cmd_publish(a, home):
    home.require()
    store, key = home.store(), home.key()
    sid = sitelib.site_id(key.public_bytes(), a.name)
    old = store.info(sid)
    version = a.version or ((old["version"] + 1) if old else 1)
    try:
        m, blocks = sitelib.pack(a.directory, key, a.name, version, access="private" if a.private else "public",
                                 listed=a.list)
    except (ValueError, OSError) as e:
        die(str(e))
    for h, b in blocks.items():
        store.put_block(h, b)
    try:
        store.put_manifest(m)
    except ValueError as e:
        die("cannot publish: %s" % e)
    print("Published %r version %d (%d pages, %s%s)" % (a.name, version, len(m["body"]["files"]), m["body"]["access"],
          ", listed" if a.list else ""))
    print("Site ID:", sid)
    try:
        from . import net
        print("Share as:", sid + "@" + net.node_address(home))
    except (ImportError, SystemExit):
        pass


def cmd_sites(a, home):
    home.require()
    store, pins = home.store(), [p.partition("@")[0] for p in home.pins()]
    me = home.key().public_bytes().hex()
    if not store.sites():
        print("(no sites yet)")
    for sid in store.sites():
        b = store.info(sid)
        flags = ("mine " if b["owner"] == me else "") + ("pinned " if sid in pins else "") + ("private" if b.get("access") == "private" else "")
        print("%s  %-20s v%-3d %2d pages  %s" % (sid, b["name"], b["version"], len(b["files"]), flags.strip()))


def cmd_ls(a, home):
    home.require()
    store, sid = _site(home, a.site)
    if not sid:
        die("site not in local store; try `alternet read %s` to fetch it" % a.site)
    b = store.info(sid)
    print("%s v%d (owner %s...)" % (b["name"], b["version"], b["owner"][:12]))
    for p in sorted(b["files"]):
        print("  " + p)


def _split_ref(ref):
    """'SITE' or 'SITE@NODEADDRESS' -> (site, address or None)."""
    site, _, addr = ref.partition("@")
    return site, (addr or None)


def cmd_read(a, home):
    home.require()
    store = home.store()
    sid = None
    a.site, hint = _split_ref(_expand(home, a.site))
    try:
        sid = store.resolve(a.site)
    except ValueError as e:
        die(str(e))
    if not sid and len(a.site) == 32:
        sid = a.site
    if not sid:
        die("unknown site %r (use the full 32-character site id to fetch from the network)" % a.site)
    if a.refresh or not store.info(sid) or store.missing(store.info(sid)):
        if a.offline:
            die("site %s is not stored locally (--offline)" % sid)
        from . import net
        try:
            status, _ = net.fetch(home, sid, wait=a.wait, hint=hint)
        except ValueError as e:
            die(str(e))
        if status == "unavailable" and not store.info(sid):
            die("site %s not found on the network (is a peer connected? see `alternet connect`)" % sid)
    body = store.info(sid)
    if not body:
        die("site not available")
    path = a.path or ("index.md" if "index.md" in body["files"] else sorted(body["files"])[0])
    try:
        sys.stdout.write(store.read(sid, path).decode("utf-8", "replace"))
    except KeyError:
        die("no such page %r; pages: %s" % (path, ", ".join(sorted(body["files"]))))
    except ValueError as e:
        die(str(e))


def cmd_name(a, home):
    home.require()
    names = home.names()
    if a.action == "list":
        for n in sorted(names):
            print("%-20s %s" % (n, names[n]))
        if not names:
            print("(no petnames; add one with: alternet name add NAME SITE[@NODEADDRESS])")
        return
    if not a.name:
        die("give a name")
    n = a.name.lower()
    if a.action == "rm":
        if names.pop(n, None) is None:
            die("no petname %r" % n)
        home.save_names(names)
        print("Removed", n)
        return
    import re
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", n) or re.fullmatch(r"[0-9a-f]{32}", n):
        die("a petname is 1-32 characters from a-z 0-9 . _ - and must not look like a 32-character site id")
    if not a.target:
        die("give the site: alternet name add NAME SITE[@NODEADDRESS]")
    sid, _, addr = a.target.partition("@")
    if len(sid) != 32 or any(c not in "0123456789abcdef" for c in sid.lower()):
        die("the site must be a full 32-character site id (optionally @NODEADDRESS)")
    if n in names and names[n] != a.target and not a.force:
        die("%r already points to %s (use --force to replace it)" % (n, names[n]))
    names[n] = a.target.lower()
    home.save_names(names)
    print("%s -> %s   (a private label on this device only; the site id is what identifies the site)" % (n, names[n]))


def cmd_directory(a, home):
    home.require()
    refs = home.directories()
    if a.action == "list":
        store = home.store()
        for ref in sorted(refs):
            dsid, _, _ = ref.partition("@")
            dsid = store.resolve(dsid) or dsid
            info = store.info(dsid)
            n = len(json.loads(store.read(dsid, "names.json").decode())) if info and "names.json" in info.get("files", {}) else 0
            print("%-45s %s" % (ref, ("%d name(s)" % n) if info else "(not fetched yet - run: alternet read %s)" % dsid))
        if not refs:
            print("(no directories subscribed; add one with: alternet directory add SITE[@ADDR])")
        return
    if not a.ref:
        die("give a directory site ref")
    if a.action == "rm":
        kept = [r for r in refs if r.partition("@")[0] != a.ref.partition("@")[0]]
        if len(kept) == len(refs):
            die("not subscribed to %r" % a.ref)
        home.save_directories(kept)
        print("Removed", a.ref)
        return
    sid = a.ref.partition("@")[0]
    if len(sid) != 32 or any(c not in "0123456789abcdef" for c in sid.lower()):
        die("the site must be a full 32-character site id (optionally @NODEADDRESS)")
    refs = [r for r in refs if r.partition("@")[0] != sid] + [a.ref.lower()]
    home.save_directories(refs)
    print("Subscribed to %s. Fetch it with: alternet read %s" % (a.ref, sid))
    print("Names from its names.json will then resolve like petnames, e.g. `alternet read NAME`.")


def cmd_pin(a, home):
    home.require()
    store = home.store()
    site, addr = _split_ref(_expand(home, a.site))
    try:
        sid = store.resolve(site) or site
    except ValueError as e:
        die(str(e))
    if len(sid) != 32:
        die("give the full 32-character site id")
    pins = [p for p in home.pins() if p.partition("@")[0] != sid]
    if not a.remove:
        pins.append(sid + ("@" + addr if addr else ""))
    home.save_pins(pins)
    print(("Unpinned " if a.remove else "Pinned ") + sid + ("" if a.remove else " (a running `alternet node` will fetch and keep it updated)"))


def cmd_bbs(a, home):
    home.require()
    from . import tui
    mode = "plain" if a.plain else ("raw" if a.raw else None)
    tui.run(home, a.site, mode=mode)


def cmd_gateway(a, home):
    home.require()
    from . import gateway
    if a.relay_hint:
        hint = a.relay_hint
    else:
        connects = home.settings().get("connect") or []
        hint = connects[0] if connects else None
    gateway.run(home, port=a.port, bind=a.bind, relay_hint=hint)


def cmd_node(a, home):
    home.require()
    from . import net
    net.run_node(home, interval=a.interval)


def _setting(home, fn):
    home.require()
    s = home.settings()
    fn(s)
    home.save_settings(s)


def cmd_connect(a, home):
    if ":" not in a.address:
        die("address must look like HOST:PORT")
    def f(s):
        if a.address not in s["connect"]:
            s["connect"].append(a.address)
    _setting(home, f)
    print("Will connect to %s (restart `alternet node` to apply)" % a.address)


def cmd_listen(a, home):
    def f(s):
        if a.port not in s["listen"]:
            s["listen"].append(a.port)
    _setting(home, f)
    print("Will listen on TCP port %d (restart `alternet node` to apply)" % a.port)


def cmd_config(a, home):
    home.require()
    s = home.settings()
    if a.auto is not None:
        s["auto"] = (a.auto == "on")
    if a.relay is not None:
        s["relay"] = (a.relay == "on")
    if a.clear:
        s["connect"], s["listen"] = [], []
    home.save_settings(s)
    for k, v in sorted(s.items()):
        print("%-10s %s" % (k, v))


def cmd_export(a, home):
    home.require()
    store, sid = _site(home, a.site)
    if not sid:
        die("unknown site")
    n = sitelib.export_bundle(store, sid, a.file)
    print("Wrote %s (%d blocks)" % (a.file, n))


def cmd_import(a, home):
    home.require()
    try:
        body, n, missing = sitelib.import_bundle(home.store(), a.file)
    except (ValueError, KeyError, OSError) as e:
        die("bundle rejected: %s" % e)
    print("Imported %r version %d (%d blocks, %d missing)" % (body["name"], body["version"], n, missing))
    print("Site ID:", body["site"])


def cmd_address(a, home):
    home.require()
    from . import net
    addr, peer = net.node_ids(home)
    print("node address:", addr)
    print("peer id:     ", peer)
    print("Others read your sites with   alternet read <site-id>@" + addr)
    print("To let this node read someone's private sites, give them the peer id for `alternet trust`.")


def _peer_id(s):
    s = s.strip().lower()
    if len(s) != 32 or any(c not in "0123456789abcdef" for c in s):
        die("a peer id is 32 hex characters (the other node's `alternet address` shows it)")
    return s


def cmd_trust(a, home):
    home.require()
    pid = _peer_id(a.peer)
    s = home.settings()
    if pid not in s["trusted"]:
        s["trusted"].append(pid)
    home.save_settings(s)
    print("Trusted", pid, "(applies immediately to a running node)")


def cmd_untrust(a, home):
    home.require()
    pid = _peer_id(a.peer)
    s = home.settings()
    s["trusted"] = [t for t in s["trusted"] if t.lower() != pid]
    home.save_settings(s)
    print("No longer trusted:", pid)


def cmd_trusted(a, home):
    home.require()
    t = home.settings()["trusted"]
    print("\n".join(t) if t else "(no trusted peers)")


def cmd_id(a, home):
    home.require()
    print("owner public key:", home.key().public_bytes().hex())
    print("home:", home.path)


def build_parser():
    p = argparse.ArgumentParser(prog="alternet", description="Alternet Core 0.1")
    p.add_argument("--home", help="state directory (default ~/.alternet or $ALTERNET_HOME)")
    p.add_argument("--version", action="version", version="alternet " + __version__)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="command")

    def add(name, fn, help, args=()):
        sp = sub.add_parser(name, help=help)
        for a in args:
            sp.add_argument(*a[0], **a[1])
        sp.set_defaults(fn=fn)
        return sp

    add("init", cmd_init, "create your node and owner key", [
        (["--no-auto"], dict(action="store_true", help="disable LAN auto-discovery")),
        (["--standalone"], dict(action="store_true", help="private Reticulum instance (run several nodes on one machine)")),
        (["--relay"], dict(action="store_true", help="forward other nodes' traffic"))])
    add("publish", cmd_publish, "publish a directory of .txt/.md pages as a signed site", [
        (["directory"], {}), (["--name"], dict(required=True)),
        (["--version"], dict(type=int, help="default: previous version + 1")),
        (["--private"], dict(action="store_true", help="serve only to peers you `trust` (replicas honor this)")),
        (["--list"], dict(action="store_true", help="signed opt-in flag: ask public directories/gateways "
            "(e.g. a relay's /directory page) to list this site. Off by default - nothing is promoted "
            "unless you ask. A directory still shows the site id either way to any peer that already has "
            "it; this only controls whether it's surfaced to people who don't."))])
    add("sites", cmd_sites, "list sites in your local store")
    add("ls", cmd_ls, "list pages of a site", [(["site"], {})])
    add("read", cmd_read, "read a page (fetches from the network if needed)", [
        (["site"], dict(help="site id or unique prefix; SITE@NODEADDRESS to name the holder")), (["path"], dict(nargs="?")),
        (["--wait"], dict(type=float, default=15, help="seconds to wait for a peer")),
        (["--refresh"], dict(action="store_true", help="check the network for a newer version")),
        (["--offline"], dict(action="store_true", help="never touch the network"))])
    add("name", cmd_name, "local petnames for sites: name add NAME SITE[@ADDR] | rm NAME | list", [
        (["action"], dict(choices=["add", "rm", "list"])), (["name"], dict(nargs="?")), (["target"], dict(nargs="?")),
        (["--force"], dict(action="store_true", help="replace an existing petname"))])
    add("directory", cmd_directory, "subscribe to a shared directory site (names.json) so its names "
        "resolve like petnames: directory add SITE[@ADDR] | rm SITE | list", [
        (["action"], dict(choices=["add", "rm", "list"])), (["ref"], dict(nargs="?"))])
    add("pin", cmd_pin, "keep a site replicated and up to date while your node runs", [
        (["site"], {}), (["--remove"], dict(action="store_true"))])
    add("bbs", cmd_bbs, "browse a site as a BBS-style menu (arrow keys where available, numbers always; b=back, q=quit)",
        [(["site"], dict(help="site id, petname, or SITE@NODEADDRESS")),
         (["--plain"], dict(action="store_true", help="use the plain print/input menu, no live keys")),
         (["--raw"], dict(action="store_true", help="force the termios/ANSI live-key renderer (used on a-Shell/iOS)"))])
    add("gateway", cmd_gateway, "serve Alternet sites to an ordinary web browser (read-only; fetches any "
        "public site id on demand, not just ones already stored here)", [
        (["--port"], dict(type=int, default=4280)),
        (["--bind"], dict(default="127.0.0.1", help="use 0.0.0.0 to let other devices on your Wi-Fi open it")),
        (["--relay-hint"], dict(default=None, help="HOST:PORT to suggest in the installer page/script "
            "(defaults to this node's own `connect` setting, which is wrong if that's a loopback address "
            "used only to reach a local relay - set this explicitly on a public gateway)"))])
    add("node", cmd_node, "run your node: announce and serve your sites, keep pins updated", [
        (["--interval"], dict(type=float, default=30, help="steady re-announce period in seconds"))])
    add("connect", cmd_connect, "add a peer to connect to (HOST:PORT)", [(["address"], {})])
    add("listen", cmd_listen, "accept connections on a TCP port", [(["port"], dict(type=int))])
    add("config", cmd_config, "show or change network settings", [
        (["--auto"], dict(choices=["on", "off"])), (["--relay"], dict(choices=["on", "off"])),
        (["--clear"], dict(action="store_true", help="remove all connect/listen entries"))])
    add("export", cmd_export, "write a site to an .altbundle file (USB/SD)", [(["site"], {}), (["file"], {})])
    add("import", cmd_import, "verify and import an .altbundle file", [(["file"], {})])
    add("trust", cmd_trust, "allow a peer (by peer id) to read your private sites", [(["peer"], {})])
    add("untrust", cmd_untrust, "remove a peer from your trusted list", [(["peer"], {})])
    add("trusted", cmd_trusted, "list trusted peers")
    add("address", cmd_address, "show your node address (for SITE@ADDRESS references)")
    add("id", cmd_id, "show your owner public key")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        a.fn(a, Home(a.home))
    except KeyboardInterrupt:
        sys.exit(130)
