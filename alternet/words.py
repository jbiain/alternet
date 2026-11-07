"""Speakable aliases for site ids: 4 pronounceable words = the first 44 bits of the id.

Not reversible to the full id and not a security boundary (44 bits can be ground to a collision). It only
selects among sites this node already knows; if it matches more than one, the caller must refuse."""
import re

_C, _V = "bdfghklmnprstvzj", "aeio"
WORDS = [a + b + c + d for a in _C for b in _V for c in _C for d in _V][:2048]
_INDEX = {w: i for i, w in enumerate(WORDS)}
PATTERN = re.compile(r"^(?:[a-z]{4}-){3}[a-z]{4}\Z")


def encode(site_id):
    """32 hex characters -> 'baka-dore-miso-lupa'."""
    n = int(site_id[:11], 16)                    # 44 bits
    return "-".join(WORDS[(n >> s) & 2047] for s in (33, 22, 11, 0))


def matches(text, site_ids):
    """The known site ids whose alias equals `text` (normally 0 or 1)."""
    text = text.strip().lower()
    if not PATTERN.match(text) or any(w not in _INDEX for w in text.split("-")):
        return []
    return [s for s in site_ids if len(s) == 32 and encode(s) == text]
