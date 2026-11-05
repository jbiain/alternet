"""The `app.json` file of an app site (docs/014): schema, validation, and a human-readable summary of what
the app asks for. Pure functions, no I/O beyond reading the file."""
import json, os, re

RUNTIMES = ("python3", "node", "native")
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
HOST = re.compile(r"^\.?[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
MAX_SECONDS, MAX_STORAGE_MB, MAX_ARGS = 6 * 3600, 1024, 64
KNOWN = {"app", "title", "run", "runtime", "needs"}
NEEDS_KNOWN = {"secrets", "net", "storage_mb", "seconds"}


def validate(raw):
    """Parse and check an app.json document (str/bytes/dict). Returns a normalised dict or raises ValueError."""
    if isinstance(raw, (bytes, str)):
        try:
            raw = json.loads(raw)
        except ValueError as e:
            raise ValueError("app.json is not valid JSON: %s" % e)
    if not isinstance(raw, dict):
        raise ValueError("app.json must be an object")
    extra = set(raw) - KNOWN
    if extra:
        raise ValueError("unknown app.json field(s): %s" % ", ".join(sorted(extra)))
    if raw.get("app") != 1:
        raise ValueError('app.json needs "app": 1')
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 80:
        raise ValueError('"title" must be a non-empty string (max 80 chars)')
    run = raw.get("run")
    if (not isinstance(run, list) or not run or len(run) > MAX_ARGS
            or not all(isinstance(x, str) and x and "\x00" not in x for x in run)):
        raise ValueError('"run" must be a non-empty list of strings (the command and its arguments)')
    if run[0].startswith("/") or ".." in run[0].split("/"):
        raise ValueError('"run"[0] must be a program name or a path inside the site, not an absolute path')
    runtime = raw.get("runtime", "native")
    if runtime not in RUNTIMES:
        raise ValueError('"runtime" must be one of %s' % ", ".join(RUNTIMES))
    needs = raw.get("needs", {})
    if not isinstance(needs, dict) or set(needs) - NEEDS_KNOWN:
        raise ValueError('"needs" may only contain: %s' % ", ".join(sorted(NEEDS_KNOWN)))
    secrets = needs.get("secrets", [])
    if not isinstance(secrets, list) or len(secrets) > 16 or not all(isinstance(x, str) and NAME.match(x) for x in secrets):
        raise ValueError('"needs.secrets" must be a list of environment variable names')
    net = needs.get("net", [])
    if (not isinstance(net, list) or len(net) > 32
            or not all(isinstance(x, str) and HOST.match(x) and re.search(r"[A-Za-z]", x.rsplit(".", 1)[-1]) for x in net)):
        raise ValueError('"needs.net" must be a list of hostnames (".example.com" allows subdomains; no IPs, no wildcards)')
    storage = needs.get("storage_mb", 0)
    seconds = needs.get("seconds", 1800)
    if not isinstance(storage, int) or isinstance(storage, bool) or not 0 <= storage <= MAX_STORAGE_MB:
        raise ValueError('"needs.storage_mb" must be an integer 0-%d' % MAX_STORAGE_MB)
    if not isinstance(seconds, int) or isinstance(seconds, bool) or not 10 <= seconds <= MAX_SECONDS:
        raise ValueError('"needs.seconds" must be an integer 10-%d' % MAX_SECONDS)
    return {"app": 1, "title": title.strip(), "run": run, "runtime": runtime,
            "needs": {"secrets": secrets, "net": net, "storage_mb": storage, "seconds": seconds}}


def check_site_dir(directory):
    """For `alternet publish`: validate app.json if the directory has one, and that `run` points at a real
    file when it names a path inside the site. Returns the normalised spec or None (not an app site)."""
    path = os.path.join(directory, "app.json")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        spec = validate(f.read())
    prog = spec["run"][0]
    if "/" in prog and not os.path.exists(os.path.join(directory, prog)):
        raise ValueError('app.json "run" points at %s, which is not in the site' % prog)
    return spec


def describe(spec):
    """The lines a permission prompt shows."""
    n = spec["needs"]
    lines = ["%s wants to run on a host (runtime: %s)." % (spec["title"], spec["runtime"])]
    lines.append("  your secrets : %s" % (", ".join(n["secrets"]) or "none"))
    lines.append("  network      : %s" % (", ".join(n["net"]) or "none"))
    lines.append("  storage      : %s" % ("%d MB" % n["storage_mb"] if n["storage_mb"] else "none"))
    lines.append("  time limit   : %d minutes" % (n["seconds"] // 60))
    return lines
