"""Signed append-only feeds (docs/015, step 4). A feed ("room") is a set of entries. Each entry is signed by its
author, names the entries its author had seen (`prev`), and is addressed by the hash of its signed body. Replicas
merge by taking the union of verified entries, so nothing needs consensus and any holder can serve any entry."""
import json, os, re, time

from . import crypto
from .site import bid, canon

ROOM_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,47}$")
MAX_TEXT, MAX_PREV, MAX_ENTRIES, MAX_SKEW = 1000, 8, 2000, 86400


def make_entry(key, room, text, prev=(), t=None):
    if not ROOM_RE.match(room):
        raise ValueError("room names are 1-48 lowercase letters, digits, . _ -")
    text = "".join(c for c in text if c.isprintable() or c == "\n")
    if not text.strip() or len(text) > MAX_TEXT:
        raise ValueError("a message must be 1-%d characters" % MAX_TEXT)
    body = {"v": 1, "room": room, "author": key.public_bytes().hex(), "t": int(t if t is not None else time.time()),
            "text": text, "prev": sorted(prev)[:MAX_PREV]}
    return {"body": body, "sig": key.sign(canon(body)).hex()}


def verify_entry(e, room=None, now=None):
    """Check structure, limits and signature. Returns (entry id, body) or raises ValueError."""
    try:
        body, sig = e["body"], bytes.fromhex(e["sig"])
        if body["v"] != 1 or not ROOM_RE.match(body["room"]) or (room is not None and body["room"] != room):
            raise ValueError("wrong room or version")
        author = bytes.fromhex(body["author"])
        if len(author) != 32 or not isinstance(body["t"], int) or not isinstance(body["text"], str):
            raise ValueError("bad field")
        if not body["text"].strip() or len(body["text"]) > MAX_TEXT:
            raise ValueError("bad text length")
        prev = body["prev"]
        if not isinstance(prev, list) or len(prev) > MAX_PREV or not all(
                isinstance(p, str) and re.fullmatch(r"[0-9a-f]{64}", p) for p in prev):
            raise ValueError("bad prev")
        if body["t"] > (now or time.time()) + MAX_SKEW:
            raise ValueError("timestamp too far in the future")
        if set(body) != {"v", "room", "author", "t", "text", "prev"}:
            raise ValueError("unexpected fields")
    except (KeyError, TypeError, AttributeError) as ex:
        raise ValueError("malformed entry: %s" % ex)
    except ValueError as ex:
        raise ValueError("malformed entry: %s" % ex)
    if not crypto.verify(author, sig, canon(body)):
        raise ValueError("bad signature")
    return bid(canon(body)), body


class Feeds:
    def __init__(self, path):
        self.path = path

    def _dir(self, room):
        return os.path.join(self.path, room)

    def rooms(self):
        return sorted(d for d in os.listdir(self.path) if ROOM_RE.match(d)) if os.path.isdir(self.path) else []

    def ids(self, room):
        d = self._dir(room)
        return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json")) if ROOM_RE.match(room) and os.path.isdir(d) else []

    def get(self, room, eid):
        if not ROOM_RE.match(room) or not re.fullmatch(r"[0-9a-f]{64}", eid):
            return None
        try:
            with open(os.path.join(self._dir(room), eid + ".json")) as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def put(self, e, room=None):
        """Verify and store. Returns True if it was new. Raises ValueError if invalid or the room is full."""
        eid, body = verify_entry(e, room)
        d = self._dir(body["room"])
        path = os.path.join(d, eid + ".json")
        if os.path.exists(path):
            return False
        os.makedirs(d, exist_ok=True)
        if len(self.ids(body["room"])) >= MAX_ENTRIES:
            raise ValueError("room is full")
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(e, f, sort_keys=True)
        os.replace(tmp, path)
        return True

    def entries(self, room):
        """All entries in one order every replica agrees on: an entry always comes after the entries it names in
        `prev`; otherwise oldest timestamp first, then id. (Unknown `prev` ids, e.g. not synced yet, are ignored.)"""
        import heapq
        items = {}
        for eid in self.ids(room):
            e = self.get(room, eid)
            if e:
                items[eid] = e
        waiting = {i: {p for p in e["body"]["prev"] if p in items and p != i} for i, e in items.items()}
        kids = {}
        for i, ps in waiting.items():
            for p in ps:
                kids.setdefault(p, []).append(i)
        heap = [(items[i]["body"]["t"], i) for i, ps in waiting.items() if not ps]
        heapq.heapify(heap)
        out = []
        while heap:
            _t, i = heapq.heappop(heap)
            out.append((i, items[i]))
            for k in kids.get(i, ()):
                waiting[k].discard(i)
                if not waiting[k]:
                    heapq.heappush(heap, (items[k]["body"]["t"], k))
        done = {i for i, _e in out}                      # entries in a cycle cannot occur (hashes), but never lose any
        out += [(i, items[i]) for i in sorted(items) if i not in done]
        return out

    def heads(self, room):
        """Entries nobody else points to: what a new message should name in `prev`."""
        es = self.entries(room)
        seen = {p for _i, e in es for p in e["body"]["prev"]}
        return [i for i, _e in es if i not in seen]


def handlers(home):
    """(ids, get) request handlers shared by every kind of node: ids(room) -> JSON list, get("room\\nid") -> entry."""
    import json as _j

    def ids(data):
        try:
            return _j.dumps(home.feeds().ids(data.decode())).encode()
        except Exception:
            return None

    def get(data):
        try:
            room, _, eid = data.decode().partition("\n")
            e = home.feeds().get(room, eid)
            return _j.dumps(e).encode() if e else None
        except Exception:
            return None
    return ids, get
