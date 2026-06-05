#!/usr/bin/env python3
"""Serve or check the local dashboard preview.

The live refresh writes tmp/dashboard_preview.html. This helper owns the local
HTTP surface used by the in-app browser: http://127.0.0.1:8765/dashboard_preview.html
"""
from __future__ import annotations

import argparse
import json
import socket
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "tmp"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PREVIEW_FILE = "dashboard_preview.html"


def preview_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}/{PREVIEW_FILE}"


def port_is_open(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def preview_status(
    *,
    directory: str | Path = DEFAULT_DIR,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> dict:
    root = Path(directory)
    preview = root / PREVIEW_FILE
    return {
        "url": preview_url(host, port),
        "directory": str(root),
        "preview_file": str(preview),
        "preview_exists": preview.is_file(),
        "server_running": port_is_open(host, port),
    }


def serve_preview(
    *,
    directory: str | Path = DEFAULT_DIR,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    root = Path(directory)
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    httpd = ThreadingHTTPServer((host, port), handler)
    print(json.dumps({**preview_status(directory=root, host=host, port=port), "serving": True}, indent=2), flush=True)
    httpd.serve_forever()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Serve or check the local dashboard preview")
    parser.add_argument("--dir", default=str(DEFAULT_DIR), help="Directory containing dashboard_preview.html")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--check", action="store_true", help="Print status and exit")
    args = parser.parse_args(argv)

    status = preview_status(directory=args.dir, host=args.host, port=args.port)
    if args.check:
        print(json.dumps(status, indent=2))
        return 0 if status["preview_exists"] else 2
    if status["server_running"]:
        print(json.dumps({**status, "serving": False, "reason": "server already running"}, indent=2))
        return 0
    if not status["preview_exists"]:
        print(json.dumps({**status, "serving": False, "reason": "preview file missing"}, indent=2))
        return 2
    serve_preview(directory=args.dir, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
