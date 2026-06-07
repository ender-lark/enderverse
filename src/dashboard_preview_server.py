#!/usr/bin/env python3
"""Serve or check the local dashboard preview.

During v1 buildout the canonical test surface is the JSX cockpit preview. The
generated HTML dashboard remains a mirror/export surface.
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
CANONICAL_PREVIEW_FILE = "cockpit_jsx_preview.html"
HTML_MIRROR_FILE = "dashboard_preview.html"


def preview_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return canonical_preview_url(host, port)


def canonical_preview_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}/{CANONICAL_PREVIEW_FILE}"


def html_mirror_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}/{HTML_MIRROR_FILE}"


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
    canonical = root / CANONICAL_PREVIEW_FILE
    html = root / HTML_MIRROR_FILE
    return {
        "primary_surface": "canonical_jsx",
        "url": canonical_preview_url(host, port),
        "canonical_url": canonical_preview_url(host, port),
        "html_url": html_mirror_url(host, port),
        "mirror_url": html_mirror_url(host, port),
        "directory": str(root),
        "preview_file": str(canonical),
        "preview_exists": canonical.is_file(),
        "canonical_file": str(canonical),
        "canonical_exists": canonical.is_file(),
        "html_preview_file": str(html),
        "html_preview_exists": html.is_file(),
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
    parser.add_argument("--dir", default=str(DEFAULT_DIR), help="Directory containing cockpit_jsx_preview.html and dashboard_preview.html")
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
        print(json.dumps({**status, "serving": False, "reason": "canonical JSX preview file missing"}, indent=2))
        return 2
    serve_preview(directory=args.dir, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
