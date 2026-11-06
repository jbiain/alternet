"""Reticulum carrier: announce, serve and fetch signed sites over encrypted Links.
Imported lazily so offline commands work without Reticulum installed."""
import json, os, sys, threading, time
from . import site as sitelib

APP, ASPECT = "alternet", "site"
MAX_ANNOUNCED = 8            # announce payload must stay small (Reticulum MTU is 500 bytes)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def _rns():
    try:
        import RNS
        return RNS
    except ImportError:
        raise SystemExit("Reticulum is not installed. Run: pip install rns")


def node_ids(home):
    """(address, peer_id) as hex. address = destination hash others connect to; peer_id = identity hash
    others put in `alternet trust`. Creates the node identity if needed; no network."""
    RNS = _rns()
    idfile = os.path.join(home.path, "node.identity")
    ident = RNS.Identity.from_file(idfile) if os.path.exists(idfile) else RNS.Identity()
    ident.to_file(idfile)
    return RNS.Destination.hash(ident, APP, ASPECT).hex(), ident.hash.hex()


def node_address(home):
    return node_ids(home)[0]


class _Listener:
    aspect_filter = "%s.%s" % (APP, ASPECT)

    def __init__(self):
        self.seen = {}       # site_id -> {dest_hash: (identity, version)}

    def received_announce(self, destination_hash, announced_identity, app_data):
        try:
            cat = json.loads(app_data.decode())
            for sid, ver in cat.items():
                self.seen.setdefault(sid, {})[destination_hash] = (announced_identity, int(ver))
        except Exception:
            return


class Session:
    def __init__(self, home):
        self.RNS = RNS = _rns()
        self.home = home
        RNS.Reticulum(home.rns_dir, loglevel=int(os.environ.get("ALTERNET_LOGLEVEL", RNS.LOG_ERROR)))
        idfile = os.path.join(home.path, "node.identity")
        self.identity = RNS.Identity.from_file(idfile) if os.path.exists(idfile) else RNS.Identity()
        self.identity.to_file(idfile)
        self.store = home.store()
        self.listener = _Listener()
        RNS.Transport.register_announce_handler(self.listener)
        self.dest = RNS.Destination(self.identity, RNS.Destination.IN, RNS.Destination.SINGLE, APP, ASPECT)
        self.dest.register_request_handler("/manifest", self._h_manifest, RNS.Destination.ALLOW_ALL)
        self.dest.register_request_handler("/block", self._h_block, RNS.Destination.ALLOW_ALL)
        self.dest.register_request_handler("/feedids", self._h_feedids, RNS.Destination.ALLOW_ALL)
        self.dest.register_request_handler("/feedget", self._h_feedget, RNS.Destination.ALLOW_ALL)

    # --- serving ---
    def _trusted(self, remote_identity):
        """Is the requesting peer (identified on the link) in our trusted list?"""
        return remote_identity is not None and remote_identity.hash.hex() in self.home.trusted()

    def _h_manifest(self, path, data, rid, lid, ri, t):
        try:
            sid = data.decode()
            m = self.store.get_manifest(sid)
            if m and self.store.is_private(sid) and not self._trusted(ri):
                return None                       # private site, untrusted peer: same answer as "not found"
        except Exception:
            return None
        return json.dumps(m).encode() if m else None

    def _h_block(self, path, data, rid, lid, ri, t):
        try:
            h = data.decode()
            blk = self.store.get_block(h)
            if blk is not None and self.store.block_is_private(h) and not self._trusted(ri):
                return None
            return blk
        except Exception:
            return None

    def _h_feedids(self, path, data, rid, lid, ri, t):
        try:
            return json.dumps(self.home.feeds().ids(data.decode())).encode()
        except Exception:
            return None

    def _h_feedget(self, path, data, rid, lid, ri, t):
        try:
            room, _, eid = data.decode().partition("\n")
            e = self.home.feeds().get(room, eid)
            return json.dumps(e).encode() if e else None
        except Exception:
            return None

    def sync_feed(self, room, addr_hex, timeout=20):
        """Pull the entries of `room` that we lack from the node at addr_hex. Every entry is verified before it
        is stored. Returns (new entries stored, rejected). Raises ValueError if the node cannot be reached."""
        from . import feed
        dh, ident = self._recall(addr_hex, timeout)
        if ident is None:
            raise ValueError("could not find %s on the network" % addr_hex)
        raw = self._request(ident, dh, "/feedids", room.encode())
        if raw is None:
            raise ValueError("that node did not answer")
        feeds, new, bad = self.home.feeds(), 0, 0
        have = set(feeds.ids(room))
        for eid in [i for i in json.loads(raw) if i not in have][:feed.MAX_ENTRIES]:
            blob = self._request(ident, dh, "/feedget", ("%s\n%s" % (room, eid)).encode())
            try:
                e = json.loads(blob)
                if feed.verify_entry(e, room)[0] != eid:
                    raise ValueError("id mismatch")
                new += 1 if feeds.put(e, room) else 0
            except (ValueError, TypeError):
                bad += 1
        return new, bad

    def catalog(self):
        cat = {}
        for sid in self.store.sites():
            if self.store.is_private(sid):
                continue                          # never advertise private sites
            cat[sid] = self.store.info(sid)["version"]
            if len(cat) >= MAX_ANNOUNCED:
                break
        return cat

    def announce(self):
        self.dest.announce(app_data=json.dumps(self.catalog()).encode())

    # --- fetching ---
    def _request(self, ident, dest_hash, path, data, timeout=20):
        RNS = self.RNS
        if not RNS.Transport.has_path(dest_hash):
            RNS.Transport.request_path(dest_hash)
            t = time.time()
            while not RNS.Transport.has_path(dest_hash) and time.time() - t < 8:
                time.sleep(0.2)
        d = RNS.Destination(ident, RNS.Destination.OUT, RNS.Destination.SINGLE, APP, ASPECT)
        link = RNS.Link(d)
        t = time.time()
        while link.status != RNS.Link.ACTIVE and time.time() - t < timeout:
            if link.status == RNS.Link.CLOSED:
                return None
            time.sleep(0.1)
        if link.status != RNS.Link.ACTIVE:
            return None
        link.identify(self.identity)              # lets the holder check us against its trusted list
        box, ev = {}, threading.Event()
        link.request(path, data=data, timeout=timeout,
                     response_callback=lambda r: (box.update(v=r.response), ev.set()),
                     failed_callback=lambda r: ev.set())
        ev.wait(timeout + 2)
        link.teardown()
        return box.get("v")

    def _recall(self, addr_hex, timeout=15):
        """(destination hash, identity) of the node at addr_hex, asking the network for a path if needed."""
        RNS = self.RNS
        try:
            dh = bytes.fromhex(addr_hex)
            if len(dh) != 16:
                raise ValueError
        except ValueError:
            raise ValueError("bad node address %r (expected 32 hex characters)" % addr_hex)
        ident = RNS.Identity.recall(dh)
        if ident is None or not RNS.Transport.has_path(dh):
            RNS.Transport.request_path(dh)
            t = time.time()
            while not RNS.Transport.has_path(dh) and time.time() - t < timeout:
                time.sleep(0.3)
            ident = RNS.Identity.recall(dh)
        return dh, ident

    def add_hint(self, sid, addr_hex, timeout=15):
        """Learn a holder from its address instead of waiting for its announce: ask the network for a
        path (a Reticulum path request). Works through relays even when announces do not arrive."""
        dh, ident = self._recall(addr_hex, timeout)
        if ident is None:
            return False
        self.listener.seen.setdefault(sid, {})[dh] = (ident, 10 ** 9)   # version unknown: always ask
        return True

    def wait_for(self, sid, wait):
        """Wait until some peer announces sid (or `wait` seconds pass). True if seen."""
        t = time.time()
        while time.time() - t < wait:
            if self.listener.seen.get(sid):
                return True
            time.sleep(0.3)
        return bool(self.listener.seen.get(sid))

    def pull(self, sid):
        """Fetch/refresh sid from the best holder. Returns (status, body) where status is
        'updated', 'current' or 'unavailable'. Verifies signature and every block before storing."""
        local = self.store.info(sid)
        lver = local["version"] if local else 0
        holders = sorted(self.listener.seen.get(sid, {}).items(), key=lambda kv: -kv[1][1])
        for dh, (ident, rver) in holders:
            if dh == self.dest.hash:
                continue
            if rver <= lver:
                return "current", local
            log("trying holder", self.RNS.prettyhexrep(dh), "version", rver)
            raw = self._request(ident, dh, "/manifest", sid.encode())
            if not raw:
                log("  holder has no manifest (not found, or you are not trusted by it)")
                continue
            try:
                m = json.loads(raw)
                body = sitelib.verify_manifest(m)
                if body["site"] != sid:
                    raise ValueError("holder sent a different site")
                if body["version"] <= lver:
                    return "current", local
                have = self.store                       # reuse blocks we already hold
                need = {h for ids in body["files"].values() for h in ids if have.get_block(h) is None}
                got = {}
                for h in sorted(need):
                    blk = self._request(ident, dh, "/block", h.encode())
                    if blk is None:
                        raise ValueError("holder is missing block %s" % h[:8])
                    sitelib.verify_block(h, blk)
                    got[h] = blk
            except Exception as e:
                log("  rejected:", e)
                continue
            for h, blk in got.items():
                self.store.put_block(h, blk)
            self.store.put_manifest(m)
            log("  verified and stored %d new blocks, version %d" % (len(got), body["version"]))
            return "updated", body
        return "unavailable", local


def fetch(home, sid, wait=15, hint=None, session=None):
    """Find sid on the network and store a verified copy. Returns (status, body). `hint` is an optional
    holder address (see `alternet address`). Pass `session` to reuse an existing long-lived Session (e.g.
    from a server process) instead of creating a new one - Reticulum allows only one instance per process,
    so a one-shot Session per call only works for short-lived commands."""
    s = session or Session(home)
    if hint:
        s.add_hint(sid, hint, timeout=min(wait, 20))
    if not s.listener.seen.get(sid) and not s.wait_for(sid, wait):
        return "unavailable", s.store.info(sid)
    time.sleep(0.5)
    return s.pull(sid)


ANNOUNCE_BURST = (0, 5, 12)      # seconds after start: quick discovery, then back off
MIN_ANNOUNCE_GAP = 5             # never announce more often than this (relays rate-limit announces)


def run_node(home, interval=30):
    """Serve and announce. Announce schedule: a short burst at start, immediately when the list of sites
    changes, then every `interval` seconds. Relays rate-limit announces per destination (Reticulum default:
    1/hour with 5 spare), so a faster steady rate gets this node silently blacklisted by such relays."""
    s = Session(home)
    log("node running; id", s.RNS.prettyhexrep(s.dest.hash), "| serving", len(s.store.sites()), "site(s)")
    start, burst = time.time(), list(ANNOUNCE_BURST)
    last_ann, last_cat, last_pin, last = 0.0, None, 0.0, {}
    try:
        while True:
            now = time.time()
            if now - last_pin >= 5:
                last_pin = now
                for entry in home.pins():
                    sid, _, addr = entry.partition("@")
                    if addr and now - last.get(entry, 0) > 60:
                        last[entry] = now
                        try:
                            s.add_hint(sid, addr, timeout=5)
                        except ValueError as e:
                            log(str(e))
                    s.pull(sid)                          # no-op unless a newer version is known
            cat = s.catalog()
            due = False
            if burst and now - start >= burst[0]:
                burst.pop(0); due = True
            elif cat != last_cat and now - last_ann >= MIN_ANNOUNCE_GAP:
                due = True
            elif now - last_ann >= interval:
                due = True
            if due:
                s.announce(); last_ann, last_cat = now, cat
            time.sleep(1)
    except KeyboardInterrupt:
        log("stopped")
