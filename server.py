#!/usr/bin/env python3
"""Perps Dashboard server — port 8766 with visitor tracking and CORS."""
import http.server
import socketserver
import sqlite3
import os
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote
import urllib.request

PORT = 8766
DIR  = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(DIR, "visits.db")

# ── Change this to any secret you like ───────────────────────────────────────
STATS_KEY = "bee2025secret"
# ─────────────────────────────────────────────────────────────────────────────


def init_db():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp  TEXT    NOT NULL,
            ip         TEXT    NOT NULL,
            path       TEXT    NOT NULL,
            user_agent TEXT
        )
    """)
    con.commit()
    con.close()


def log_visit(ip: str, path: str, user_agent: str):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    con = sqlite3.connect(DB)
    con.execute(
        "INSERT INTO visits (timestamp, ip, path, user_agent) VALUES (?,?,?,?)",
        (ts, ip, path, user_agent)
    )
    con.commit()
    con.close()


def get_stats() -> dict:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    total      = con.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
    unique_ips = con.execute("SELECT COUNT(DISTINCT ip) FROM visits").fetchone()[0]
    by_ip      = con.execute(
        "SELECT ip, COUNT(*) as cnt FROM visits GROUP BY ip ORDER BY cnt DESC"
    ).fetchall()
    recent     = con.execute(
        "SELECT timestamp, ip, path, user_agent FROM visits ORDER BY id DESC LIMIT 50"
    ).fetchall()
    con.close()
    return {
        "total": total,
        "unique_ips": unique_ips,
        "by_ip": [dict(r) for r in by_ip],
        "recent": [dict(r) for r in recent],
    }


def build_stats_html(s: dict) -> bytes:
    by_ip_rows = "".join(
        f"<tr><td>{r['ip']}</td><td>{r['cnt']}</td></tr>"
        for r in s["by_ip"]
    )
    recent_rows = "".join(
        f"<tr><td>{r['timestamp']} UTC</td><td>{r['ip']}</td>"
        f"<td>{r['path']}</td><td style='font-size:11px;color:#9ca3af'>{r['user_agent'][:60]}</td></tr>"
        for r in s["recent"]
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>📊 Perps — Visitor Stats</title>
  <style>
    body{{font-family:'Segoe UI',sans-serif;background:#0d0f14;color:#f1f3fa;padding:32px;}}
    h1{{color:#f5c518;margin-bottom:4px;}}
    .sub{{color:#9ca3af;font-size:13px;margin-bottom:28px;}}
    .cards{{display:flex;gap:20px;margin-bottom:32px;flex-wrap:wrap;}}
    .card{{background:#13161f;border:1px solid #2e3548;border-radius:12px;
           padding:20px 28px;min-width:140px;}}
    .card .val{{font-size:36px;font-weight:800;color:#f5c518;}}
    .card .lbl{{font-size:12px;color:#9ca3af;margin-top:4px;}}
    table{{width:100%;border-collapse:collapse;background:#13161f;
           border:1px solid #252a38;border-radius:10px;overflow:hidden;
           font-size:13px;}}
    th{{background:#1a1e2a;color:#9ca3af;font-size:10px;text-transform:uppercase;
        letter-spacing:.8px;padding:10px 14px;text-align:left;}}
    td{{padding:8px 14px;border-bottom:1px solid #252a38;}}
    tr:last-child td{{border:none;}}
    h2{{font-size:15px;color:#f1f3fa;margin:28px 0 10px;}}
  </style>
</head>
<body>
  <h1>📊 Visitor Statistics</h1>
  <div class="sub">Perps Point Cost Calculator — developer view only</div>

  <div class="cards">
    <div class="card"><div class="val">{s["total"]}</div><div class="lbl">Total visits</div></div>
    <div class="card"><div class="val">{s["unique_ips"]}</div><div class="lbl">Unique IPs</div></div>
  </div>

  <h2>Visits per IP</h2>
  <table>
    <thead><tr><th>IP Address</th><th>Visits</th></tr></thead>
    <tbody>{by_ip_rows}</tbody>
  </table>

  <h2>Recent 50 visits</h2>
  <table>
    <thead><tr><th>Time (UTC)</th><th>IP</th><th>Path</th><th>User-Agent</th></tr></thead>
    <tbody>{recent_rows}</tbody>
  </table>
</body>
</html>"""
    return html.encode("utf-8")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def log_message(self, format, *args):
        print(f"[PERPS] {self.address_string()} - {format % args}")

    def end_headers(self):
        # Enable CORS for all responses
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS, POST")
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        # Handle CORS preflight
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # ── Stats endpoint ────────────────────────────────────────────────────
        if parsed.path == "/stats":
            key = params.get("key", [""])[0]
            if key != STATS_KEY:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"403 Forbidden")
                return
            body = build_stats_html(get_stats())
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # ── Image proxy (for html2canvas CORS) ───────────────────────────────
        if parsed.path == "/img-proxy":
            url = params.get("url", [""])[0]
            if not url or not url.startswith("https://"):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"400 Bad Request")
                return
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = resp.read()
                    ct = resp.headers.get("Content-Type", "image/png")
                self.send_response(200)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_response(502)
                self.end_headers()
                self.wfile.write(b"502 Proxy Error")
            return

        # ── Tracking endpoint (pinged from JS) ────────────────────────────────
        if parsed.path == "/track":
            # Extract real IP (check for Proxy headers first)
            ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
            ua = self.headers.get("User-Agent", "Unknown")
            page = params.get("page", ["GitHubPages"])[0]
            log_visit(ip, page, ua)
            
            # Respond with a tiny 1x1 transparent GIF (classic tracker style)
            pixel = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
            self.send_response(200)
            self.send_header("Content-Type", "image/gif")
            self.send_header("Content-Length", str(len(pixel)))
            self.end_headers()
            self.wfile.write(pixel)
            return

        # ── Log local visits (if running directly) ────────────────────────────
        if parsed.path in ("/", "/index.html"):
            ip = self.client_address[0]
            ua = self.headers.get("User-Agent", "Unknown")
            log_visit(ip, "LocalHost" if "localhost" in self.headers.get("Host", "") else "Direct", ua)

        # ── Serve static files as usual ───────────────────────────────────────
        super().do_GET()


init_db()
print(f"✅  Perps Dashboard  → http://localhost:{PORT}")
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
