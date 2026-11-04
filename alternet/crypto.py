"""Ed25519 shim. Prefers `cryptography`; falls back to Reticulum's bundled pure-Python Ed25519
(needed where `cryptography` cannot be installed, e.g. iOS a-Shell). Both read/write the raw
32-byte seed, so keys and signatures are interchangeable. Set ALT_PURE=1 to force the fallback."""
import os

try:
    if os.environ.get("ALT_PURE"):
        raise ImportError
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey as _Priv, Ed25519PublicKey as _Pub)
    from cryptography.hazmat.primitives import serialization as _ser
    BACKEND = "cryptography"

    def _from_seed(b): return _Priv.from_private_bytes(b)
    def _seed(k): return k.private_bytes(_ser.Encoding.Raw, _ser.PrivateFormat.Raw, _ser.NoEncryption())
    def _pub(k): return k.public_key().public_bytes(_ser.Encoding.Raw, _ser.PublicFormat.Raw)
except ImportError:
    from RNS.Cryptography.Ed25519 import Ed25519PrivateKey as _Priv, Ed25519PublicKey as _Pub
    BACKEND = "rns-pure"

    def _from_seed(b): return _Priv.from_private_bytes(b)
    def _seed(k): return k.private_bytes()
    def _pub(k): return k.public_key().public_bytes()


def _verify(pub, sig, msg):
    _Pub.from_public_bytes(pub).verify(sig, msg)


class SigningKey:
    """Owner key. File = raw 32-byte seed, mode 0600."""
    def __init__(self, priv): self._p = priv

    @classmethod
    def load_or_create(cls, path):
        if os.path.exists(path):
            with open(path, "rb") as f:
                return cls(_from_seed(f.read()))
        k = _Priv.generate()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(_seed(k))
        return cls(k)

    def public_bytes(self): return _pub(self._p)
    def sign(self, data): return self._p.sign(data)


def verify(pub: bytes, sig: bytes, msg: bytes) -> bool:
    try:
        _verify(pub, sig, msg)
        return True
    except Exception:
        return False
