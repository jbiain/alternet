"""Carrier-independent signed site: content blocks, signed manifest, local store, .altbundle files.
No networking and no Reticulum import here (see docs/004-bundle-format.md)."""
import base64, hashlib, json, os
from . import crypto

BLOCK = 32 * 1024
MAX_FILE = 5 * 1024 * 1024      # v0.1 sanity cap per file
ACCESS = ("public", "private")  # "private": served only to trusted peers (see docs/003)


def bid(data): return hashlib.sha256(data).hexdigest()
def canon(obj): return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def site_id(owner_pub: bytes, name: str) -> str:
    return hashlib.sha256(owner_pub + name.encode()).hexdigest()[:32]


OWNER_TAG_LEN = 6


def owner_tag(owner_hex):
    """Short, readable tag for an owner key. Display and convenience only: short tags can collide, so the
    full key stays the identity (see docs/012-names.md)."""
    return owner_hex[:OWNER_TAG_LEN]


def display_name(info):
    return "%s@%s" % (info["name"], owner_tag(info["owner"]))


def pack(directory, key, name, version, access="public", listed=False):
    blocks, files = {}, {}
    for root, _, fs in os.walk(directory):
        for f in sorted(fs):
            if f.startswith("."):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, directory).replace(os.sep, "/")
            with open(p, "rb") as fh:
                data = fh.read()
            if len(data) > MAX_FILE:
                raise ValueError("%s is larger than %d bytes" % (rel, MAX_FILE))
            ids = []
            for i in range(0, max(len(data), 1), BLOCK):
                chunk = data[i:i + BLOCK]
                blocks[bid(chunk)] = chunk
                ids.append(bid(chunk))
            files[rel] = ids
    if not files:
        raise ValueError("no files to publish in %s" % directory)
    if access not in ACCESS:
        raise ValueError("access must be 'public' or 'private'")
    pub = key.public_bytes()
    body = {"v": 1, "name": name, "version": version, "owner": pub.hex(), "site": site_id(pub, name),
            "files": files, "access": access, "listed": bool(listed)}
    return {"body": body, "sig": key.sign(canon(body)).hex()}, blocks


def verify_manifest(m):
    """Return the manifest body if the signature and site id check out, else raise ValueError."""
    try:
        body = m["body"]
        pub = bytes.fromhex(body["owner"])
        sig = bytes.fromhex(m["sig"])
        if not crypto.verify(pub, sig, canon(body)):
            raise ValueError("bad manifest signature")
        if body["site"] != site_id(pub, body["name"]):
            raise ValueError("site id does not match owner/name")
        if not isinstance(body["version"], int) or not isinstance(body["files"], dict):
            raise ValueError("malformed manifest")
        if body.get("access", "public") not in ACCESS:
            raise ValueError("malformed manifest (access)")
        return body
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError("malformed manifest: %r" % (e,))


def verify_block(h, data):
    if bid(data) != h:
        raise ValueError("block hash mismatch")


def _safe(s, n):
    return isinstance(s, str) and len(s) == n and all(c in "0123456789abcdef" for c in s)


class Store:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.join(path, "blocks"), exist_ok=True)
        os.makedirs(os.path.join(path, "manifests"), exist_ok=True)

    def _m(self, sid): return os.path.join(self.path, "manifests", sid + ".json")

    def put_block(self, h, data):
        verify_block(h, data)
        p = os.path.join(self.path, "blocks", h)
        tmp = p + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, p)

    def get_block(self, h):
        if not _safe(h, 64):
            return None
        p = os.path.join(self.path, "blocks", h)
        if not os.path.exists(p):
            return None
        with open(p, "rb") as f:
            return f.read()

    def get_manifest(self, sid):
        if not _safe(sid, 32) or not os.path.exists(self._m(sid)):
            return None
        with open(self._m(sid)) as f:
            return json.load(f)

    def put_manifest(self, m):
        body = verify_manifest(m)
        old = self.get_manifest(body["site"])
        if old and old["body"]["version"] >= body["version"]:
            raise ValueError("stale version")        # rollback protection
        tmp = self._m(body["site"]) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(m, f)
        os.replace(tmp, self._m(body["site"]))
        return body

    def sites(self):
        return sorted(f[:-5] for f in os.listdir(os.path.join(self.path, "manifests")) if f.endswith(".json"))

    def info(self, sid):
        m = self.get_manifest(sid)
        return verify_manifest(m) if m else None

    def is_private(self, sid):
        b = self.info(sid)
        return bool(b) and b.get("access", "public") == "private"

    def block_is_private(self, h):
        """True if any private site references this block (a block hash alone must not leak private content)."""
        for sid in self.sites():
            b = self.info(sid)
            if b.get("access", "public") == "private" and any(h in ids for ids in b["files"].values()):
                return True
        return False

    def missing(self, body):
        return [h for ids in body["files"].values() for h in ids if self.get_block(h) is None]

    def read(self, sid, path):
        body = self.info(sid)
        if not body or path not in body["files"]:
            raise KeyError(path)
        parts = [self.get_block(h) for h in body["files"][path]]
        if any(p is None for p in parts):
            raise ValueError("site is not fully stored locally")
        return b"".join(parts)

    def find_named(self, name, tag):
        """The one stored site called `name` whose owner key starts with `tag`; None if there is none.
        Raises ValueError if the tag is not enough to tell two owners' sites apart."""
        hits = []
        for sid in self.sites():
            b = self.info(sid)
            if b["name"].lower() == name and b["owner"].startswith(tag):
                hits.append(sid)
        if len(hits) > 1:
            raise ValueError("%s@%s is ambiguous; use a longer owner tag or the site id" % (name, tag))
        return hits[0] if hits else None

    def resolve(self, prefix):
        """Accept a full site id or a unique prefix."""
        hits = [s for s in self.sites() if s.startswith(prefix)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ValueError("ambiguous site id prefix %r" % prefix)
        return None


# ---- .altbundle: one JSON file, usable over USB/SD/any stream ----
def export_bundle(store, sid, path):
    body = store.info(sid)
    if not body:
        raise ValueError("unknown site %s" % sid)
    blocks = {h: base64.b64encode(store.get_block(h)).decode()
              for ids in body["files"].values() for h in ids if store.get_block(h) is not None}
    with open(path, "w") as f:
        json.dump({"altbundle": 1, "manifest": store.get_manifest(sid), "blocks": blocks}, f)
    return len(blocks)


def import_bundle(store, path):
    """Verify everything first; store nothing unless manifest and all present blocks check out."""
    with open(path) as f:
        b = json.load(f)
    if b.get("altbundle") != 1:
        raise ValueError("not an altbundle file")
    body = verify_manifest(b["manifest"])
    wanted = {h for ids in body["files"].values() for h in ids}
    blocks = {}
    for h, enc in b["blocks"].items():
        if h not in wanted:
            raise ValueError("unexpected block in bundle")
        data = base64.b64decode(enc)
        verify_block(h, data)
        blocks[h] = data
    store.put_manifest(b["manifest"])               # also enforces the rollback check
    for h, data in blocks.items():
        store.put_block(h, data)
    return body, len(blocks), len(wanted - set(blocks))
