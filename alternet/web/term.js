(function () {
  var q = new URLSearchParams(location.search), target = q.get("open") || "";
  var box = document.getElementById("form"), screen = document.getElementById("screen"), status = document.getElementById("status");
  document.getElementById("target").value = target;
  document.getElementById("go").onclick = function () {
    var v = document.getElementById("target").value.trim();
    if (v) location.search = "?open=" + encodeURIComponent(v);
  };
  if (!target) return;
  box.style.display = "none"; screen.style.display = "block";
  var cols = Math.max(40, Math.min(200, Math.floor(innerWidth / 9.2))), rows = Math.max(12, Math.min(60, Math.floor((innerHeight - 70) / 18)));
  var term = new Terminal({cols: cols, rows: rows, cursorBlink: true, fontFamily: "Menlo, Consolas, monospace", fontSize: 15, scrollback: 2000});
  term.open(document.getElementById("term")); term.focus();
  var ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host +
                         "/terminal/ws?open=" + encodeURIComponent(target) + "&cols=" + cols + "&rows=" + rows);
  ws.binaryType = "arraybuffer";
  var enc = new TextEncoder();
  ws.onopen = function () { status.textContent = "connected through this gateway. Ctrl-] disconnects."; };
  ws.onmessage = function (e) { term.write(new Uint8Array(e.data)); };
  ws.onclose = function () { status.textContent = "disconnected"; term.write("\r\n[connection closed]\r\n"); };
  term.onData(function (d) { if (ws.readyState === 1) ws.send(enc.encode(d)); });
  document.getElementById("quit").onclick = function () { ws.close(); };
})();
