"""Per-user state directory (default ~/.alternet, override with --home or $ALTERNET_HOME)."""
import json, os
from . import crypto
from .site import Store

def _load(path):
    with open(path) as f:
        return json.load(f)


DEFAULT_SETTINGS = {"auto": True, "listen": [], "connect": [], "relay": False, "standalone": False, "trusted": []}


def _default_path():
    """~/.alternet, unless the home directory is read-only (iOS a-Shell): then ~/Documents/.alternet."""
    home = os.path.expanduser("~")
    default = os.path.join(home, ".alternet")
    if os.path.exists(default) or os.access(home, os.W_OK):
        return default
    docs = os.path.join(home, "Documents")
    return os.path.join(docs, ".alternet") if os.path.isdir(docs) else default


class Home:
    def __init__(self, path=None):
        self.path = os.path.abspath(os.path.expanduser(path or os.environ.get("ALTERNET_HOME") or _default_path()))

    # paths
    @property
    def rns_dir(self): return os.path.join(self.path, "reticulum")
    @property
    def settings_file(self): return os.path.join(self.path, "settings.json")
    @property
    def pins_file(self): return os.path.join(self.path, "pins.json")
    @property
    def key_file(self): return os.path.join(self.path, "owner.key")

    def exists(self): return os.path.exists(self.settings_file)

    def require(self):
        if not self.exists():
            raise SystemExit("No Alternet home at %s. Run: alternet init" % self.path)

    def init(self, **overrides):
        os.makedirs(self.rns_dir, exist_ok=True)
        s = dict(DEFAULT_SETTINGS)
        s.update({k: v for k, v in overrides.items() if v is not None})
        if not self.exists():
            self.save_settings(s)
        crypto.SigningKey.load_or_create(self.key_file)
        self.store()
        return self.settings()

    def settings(self):
        s = dict(DEFAULT_SETTINGS)
        if os.path.exists(self.settings_file):
            s.update(_load(self.settings_file))
        return s

    def save_settings(self, s):
        os.makedirs(self.path, exist_ok=True)
        with open(self.settings_file, "w") as f:
            json.dump(s, f, indent=2)
        self.write_rns_config(s)

    def trusted(self):
        return set(t.lower() for t in self.settings().get("trusted", []))

    def key(self): return crypto.SigningKey.load_or_create(self.key_file)
    def store(self): return Store(os.path.join(self.path, "store"))

    @property
    def names_file(self): return os.path.join(self.path, "names.json")

    def names(self):
        """Local petnames: {name: "SITEID" or "SITEID@NODEADDRESS"}. Private to this home; never sent anywhere."""
        return _load(self.names_file) if os.path.exists(self.names_file) else {}

    def save_names(self, names):
        os.makedirs(self.path, exist_ok=True)
        with open(self.names_file, "w") as f:
            json.dump(names, f, indent=2, sort_keys=True)

    @property
    def name_pins_file(self): return os.path.join(self.path, "name_pins.json")

    def name_pins(self):
        """First-use pins: {name: site id} for names learned from a shared directory."""
        return _load(self.name_pins_file) if os.path.exists(self.name_pins_file) else {}

    def save_name_pins(self, pins):
        os.makedirs(self.path, exist_ok=True)
        with open(self.name_pins_file, "w") as f:
            json.dump(pins, f, indent=2, sort_keys=True)

    @property
    def forms_file(self): return os.path.join(self.path, "form_values.json")

    def form_values(self, sid):
        """What you typed into a site's form fields: private to this machine, never sent anywhere."""
        allv = _load(self.forms_file) if os.path.exists(self.forms_file) else {}
        return dict(allv.get(sid, {}))

    def save_form_values(self, sid, values):
        allv = _load(self.forms_file) if os.path.exists(self.forms_file) else {}
        allv[sid] = values
        os.makedirs(self.path, exist_ok=True)
        with open(self.forms_file, "w") as f:
            json.dump(allv, f)

    @property
    def grants_file(self): return os.path.join(self.path, "app_grants.json")

    def app_grants(self):
        """{site id: digest of the app.json you accepted}. A changed app.json asks again."""
        return _load(self.grants_file) if os.path.exists(self.grants_file) else {}

    def save_app_grants(self, g):
        os.makedirs(self.path, exist_ok=True)
        with open(self.grants_file, "w") as f:
            json.dump(g, f)

    def app_data_dir(self, site):
        """Where an app site's saved files live. They are yours: sent to a host for a session, then returned."""
        return os.path.join(self.path, "app_data", site)

    @property
    def directories_file(self): return os.path.join(self.path, "directories.json")

    def directories(self):
        """Subscribed directory sites: ["SITEID" or "SITEID@ADDR", ...]. A directory is an ordinary
        Alternet site (see `alternet publish`) whose `names.json` page maps name -> site ref; anyone can
        publish one, and subscribing to one is a purely local choice, same trust model as petnames but
        shareable, because the mapping is a signed site instead of a private file. See docs/007."""
        return _load(self.directories_file) if os.path.exists(self.directories_file) else []

    def save_directories(self, refs):
        with open(self.directories_file, "w") as f:
            json.dump(sorted(set(refs)), f)

    def pins(self):
        return _load(self.pins_file) if os.path.exists(self.pins_file) else []

    def save_pins(self, pins):
        with open(self.pins_file, "w") as f:
            json.dump(sorted(set(pins)), f)

    def write_rns_config(self, s=None):
        s = s or self.settings()
        yn = lambda b: "Yes" if b else "No"
        out = ["[reticulum]",
               "  enable_transport = %s" % yn(s["relay"]),
               "  share_instance = %s" % yn(not s["standalone"]),
               "[logging]", "  loglevel = 1", "[interfaces]"]
        # Reticulum relays rate-limit announces per destination (default 1/hour, grace 5) and then silently
        # stop forwarding them for about an hour. Relax that on relays we configure (see docs/005).
        rate = (["    announce_rate_target = 20", "    announce_rate_grace = 5", "    announce_rate_penalty = 0"]
                if s["relay"] else [])
        if s["auto"]:
            out += ["  [[Auto]]", "    type = AutoInterface", "    enabled = yes"]
        for i, port in enumerate(s["listen"]):
            out += ["  [[Listen%d]]" % i, "    type = TCPServerInterface", "    enabled = yes",
                    "    listen_ip = 0.0.0.0", "    listen_port = %d" % int(port)] + rate
        for i, hp in enumerate(s["connect"]):
            host, port = hp.rsplit(":", 1)
            out += ["  [[Connect%d]]" % i, "    type = TCPClientInterface", "    enabled = yes",
                    "    target_host = %s" % host, "    target_port = %d" % int(port)] + rate
        os.makedirs(self.rns_dir, exist_ok=True)
        with open(os.path.join(self.rns_dir, "config"), "w") as f:
            f.write("\n".join(out) + "\n")
