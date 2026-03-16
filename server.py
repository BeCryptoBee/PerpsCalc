#!/usr/bin/env python3
"""Simple HTTP server for Perps Dashboard — port 8765"""
import http.server
import socketserver
import os

PORT = 8765
DIR = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)
    def log_message(self, format, *args):
        print(f"[PERPS] {self.address_string()} - {format % args}")

print(f"✅  Perps Dashboard → http://localhost:{PORT}")
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
