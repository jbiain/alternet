"""A tiny shared chat room. Every visitor runs their own copy; they meet in the host's shared directory
(ALTERNET_SHARED). Standard library only. Messages are one JSON line each, appended atomically."""
import json, os, select, sys, time

DIR = os.environ.get("ALTERNET_SHARED", "/work/shared")
LOG = os.path.join(DIR, "room.log")
ME = (os.environ.get("ALTERNET_PEER") or "guest")[:6]
MAX_LINE, KEEP = 400, 200 * 1024


def clean(s):
    return "".join(c for c in s if c.isprintable())[:MAX_LINE]


def say(nick, text):
    line = json.dumps({"t": int(time.time()), "n": nick, "m": text}) + "\n"
    fd = os.open(LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line.encode())
    finally:
        os.close(fd)
    if os.path.getsize(LOG) > KEEP:                       # keep the log small: drop the older half
        with open(LOG, "rb") as f:
            data = f.read()
        tail = data[len(data) // 2:]
        tail = tail[tail.find(b"\n") + 1:]
        tmp = LOG + ".tmp%d" % os.getpid()
        with open(tmp, "wb") as f:
            f.write(tail)
        os.replace(tmp, LOG)


def show(rec):
    print("%s <%s> %s" % (time.strftime("%H:%M", time.localtime(rec.get("t", 0))), clean(str(rec.get("n", "?"))), clean(str(rec.get("m", "")))), flush=True)


def main():
    os.makedirs(DIR, exist_ok=True)
    print("Shared room. You are %s. Type a message and press Enter; Ctrl-] leaves.\n" % ME, flush=True)
    pos = 0
    if os.path.exists(LOG):
        with open(LOG, "rb") as f:
            data = f.read()
        for ln in data.splitlines()[-20:]:
            try:
                show(json.loads(ln))
            except ValueError:
                pass
        pos = len(data)
    say("*", "%s joined" % ME)
    last = 0.0
    while True:
        if select.select([sys.stdin], [], [], 0.5)[0]:
            text = sys.stdin.readline()
            if not text:
                break
            text = clean(text.strip())
            if text and time.time() - last > 0.5:          # at most two messages a second per visitor
                last = time.time()
                say(ME, text)
        if os.path.exists(LOG):
            with open(LOG, "rb") as f:
                if os.path.getsize(LOG) < pos:
                    pos = 0
                f.seek(pos)
                new = f.read()
            if new:
                pos += len(new)
                for ln in new.splitlines():
                    try:
                        show(json.loads(ln))
                    except ValueError:
                        pass


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        pass
