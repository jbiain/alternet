(function () {
  var screenEl = document.getElementById("screen"), status = document.getElementById("status");
  var apps = [];
  try { apps = JSON.parse(document.getElementById("apps").textContent) || []; } catch (e) {}
  var cols = Math.max(40, Math.min(200, Math.floor(innerWidth / 9.2))), rows = Math.max(12, Math.min(60, Math.floor((innerHeight - 70) / 18)));
  var term = new Terminal({cols: cols, rows: rows, cursorBlink: true, fontFamily: "Menlo, Consolas, monospace", fontSize: 15, scrollback: 2000});
  term.open(document.getElementById("term")); term.focus();
  var enc = new TextEncoder(), ws = null, mode = "menu", sel = 0, note = "", typed = "";
  var items = apps.map(function (a) { return {label: a.name, desc: a.desc, run: function () { connect(a.address); }}; });
  items.push({label: "open an address...", desc: "ADDRESS, ADDRESS/APP or SITE@ADDRESS", run: function () { mode = "input"; typed = ""; draw(); }});
  items.push({label: "known sites", desc: "the BBS and site directory", run: function () { location.href = "/bbs"; }});
  items.push({label: "for AI agents", desc: "plain-text description", run: function () { location.href = "/llms.txt"; }});
  items.push({label: "run your own node", desc: "curl -fsSL " + location.origin + "/install.sh | sh", run: function () { note = "Run this in a terminal:  curl -fsSL " + location.origin + "/install.sh | sh"; draw(); }});

  function pad(s, n) { s = String(s); return s.length >= n ? s.slice(0, n) : s + new Array(n - s.length + 1).join(" "); }
  function draw() {
    var w = Math.min(cols - 2, 72), inner = w - 2, out = "\x1b[2J\x1b[H\x1b[?25l\r\n";
    function line(t, style) { out += " │" + (style || "") + pad(t, inner) + "\x1b[0m│\r\n"; }
    var bar = new Array(inner + 1).join("─");
    out += " ┌" + bar + "┐\r\n";
    line("  ALTERNET  -  a network of signed sites and apps", "\x1b[1m");
    out += " ├" + bar + "┤\r\n";
    if (mode === "input") {
      line(""); line("  Address:", "\x1b[2m"); line("  " + typed + "_"); line("");
      line("  Enter connects, Esc goes back", "\x1b[2m");
    } else {
      line("");
      items.forEach(function (it, i) {
        var on = i === sel, d = it.desc ? "  " + it.desc : "";
        line((on ? " > " : "   ") + pad(it.label, 18) + d.slice(0, Math.max(0, inner - 24)), on ? "\x1b[7m" : "");
      });
      line("");
    }
    out += " └" + bar + "┘\r\n";
    if (note) out += "\r\n \x1b[33m" + note + "\x1b[0m\r\n";
    out += "\r\n \x1b[2m" + (mode === "input" ? "" : "up/down move, Enter opens, 1-9 jump") + "\x1b[0m";
    term.write(out);
  }

  function connect(target) {
    mode = "session"; note = ""; status.textContent = "connecting...";
    term.reset(); term.write("\x1b[?25h");
    history.replaceState(null, "", "/?open=" + encodeURIComponent(target));
    var got = false, opened = Date.now();
    ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host +
                       "/terminal/ws?open=" + encodeURIComponent(target) + "&cols=" + cols + "&rows=" + rows);
    ws.binaryType = "arraybuffer";
    ws.onopen = function () { status.textContent = "connected through this gateway"; };
    ws.onmessage = function (e) { got = true; term.write(new Uint8Array(e.data)); };
    ws.onclose = function () {
      var secs = (Date.now() - opened) / 1000;
      note = !got ? "Could not start that session (host unreachable, or the gateway is full). Try again."
        : secs >= 890 ? "Session timed out after a period of inactivity." : "Session ended.";
      ws = null; mode = "menu"; status.textContent = ""; history.replaceState(null, "", "/");
      term.reset(); draw();
    };
  }

  term.onData(function (d) {
    if (mode === "session") { if (ws && ws.readyState === 1) ws.send(enc.encode(d)); return; }
    if (mode === "input") {
      if (d === "\x1b") { mode = "menu"; draw(); }
      else if (d === "\r") { var v = typed.trim(); if (v) connect(v); }
      else if (d === "\x7f") { typed = typed.slice(0, -1); draw(); }
      else if (d.charCodeAt(0) >= 32) { typed += d.replace(/[\x00-\x1f\x7f]/g, ""); draw(); }
      return;
    }
    note = "";
    if (d === "\x1b[A" || d === "k") sel = (sel + items.length - 1) % items.length;
    else if (d === "\x1b[B" || d === "j") sel = (sel + 1) % items.length;
    else if (/^[1-9]$/.test(d) && items[+d - 1]) sel = +d - 1;
    else if (d === "\r" || d === " ") { items[sel].run(); return; }
    else return;
    draw();
  });

  var open = new URLSearchParams(location.search).get("open");
  if (open) connect(open); else draw();
})();
