#!/usr/bin/env python3
"""Serve or check the local operator dashboard preview.

The HTML dashboard is the default operator surface. The JSX preview remains
available as an internal validation/parity surface.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "tmp"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
CANONICAL_PREVIEW_FILE = "dashboard_preview.html"
JSX_VALIDATION_FILE = "cockpit_jsx_preview.html"
HTML_MIRROR_FILE = "dashboard_preview.html"
ORIGIN_STATUS_PATH = "/__dashboard_origin.json"
STAMP_RE = re.compile(
    r'<div\s+class="stamp"(?P<attrs>[^>]*)>(?P<body>.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
TITLE_RE = re.compile(r'title="(?P<title>[^"]*)"', re.IGNORECASE)


def preview_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return canonical_preview_url(host, port)


def canonical_preview_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}/{CANONICAL_PREVIEW_FILE}"


def jsx_validation_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}/{JSX_VALIDATION_FILE}"


def html_mirror_url(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}/{HTML_MIRROR_FILE}"


def port_is_open(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_preview_stamp(html: str) -> dict:
    match = STAMP_RE.search(html)
    if not match:
        return {"present": False, "title": "", "text": ""}
    attrs = match.group("attrs") or ""
    title_match = TITLE_RE.search(attrs)
    title = title_match.group("title") if title_match else ""
    body = re.sub(r"<[^>]+>", " ", match.group("body") or "")
    return {"present": True, "title": _clean_text(title), "text": _clean_text(body)}


def preview_file_metadata(path: str | Path) -> dict:
    preview = Path(path)
    if not preview.is_file():
        return {"exists": False, "path": str(preview), "sha256": "", "stamp": {"present": False, "title": "", "text": ""}}
    raw = preview.read_bytes()
    body = raw.decode("utf-8", errors="replace")
    return {
        "exists": True,
        "path": str(preview),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "stamp": extract_preview_stamp(body),
    }


def _fetch_text(url: str, *, timeout: float = 1.5) -> dict:
    try:
        request = Request(url, headers={"Cache-Control": "no-cache"})
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            body = raw.decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status_code": response.status,
                "url": url,
                "text": body,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "error": "",
            }
    except (OSError, URLError) as exc:
        return {"ok": False, "status_code": 0, "url": url, "text": "", "error": str(exc)}


def served_origin_status(
    *,
    directory: str | Path = DEFAULT_DIR,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    fetcher=_fetch_text,
) -> dict:
    status = preview_status(directory=directory, host=host, port=port)
    local = preview_file_metadata(status["canonical_file"])
    result = {
        "status": "not_checked",
        "ok": False,
        "problems": [],
        "local": local,
        "served": {"available": False, "sha256": "", "stamp": {"present": False, "title": "", "text": ""}},
        "server_report": None,
    }

    if not local["exists"]:
        result["status"] = "missing_local_preview"
        result["problems"].append("local dashboard_preview.html is missing")
        return result
    if not status["server_running"]:
        result["status"] = "not_running"
        result["problems"].append("dashboard preview server is not listening")
        return result

    served_page = fetcher(status["canonical_url"])
    if not served_page["ok"]:
        result["status"] = "served_preview_unreachable"
        result["problems"].append(f"served preview fetch failed: {served_page['error']}")
        return result

    served_text = served_page["text"]
    result["served"] = {
        "available": True,
        "status_code": served_page["status_code"],
        "sha256": served_page.get("sha256") or hashlib.sha256(served_text.encode("utf-8")).hexdigest(),
        "stamp": extract_preview_stamp(served_text),
    }

    endpoint = fetcher(f"http://{host}:{port}{ORIGIN_STATUS_PATH}")
    if endpoint["ok"]:
        try:
            result["server_report"] = json.loads(endpoint["text"])
        except json.JSONDecodeError:
            result["problems"].append("origin endpoint returned invalid JSON")

    if result["served"]["sha256"] != local["sha256"]:
        result["problems"].append("served dashboard_preview.html does not match this worktree's preview file")
    if result["served"]["stamp"] != local["stamp"]:
        result["problems"].append("served dashboard stamp does not match this worktree's preview stamp")
    if result["server_report"] and result["server_report"].get("directory") != status["directory"]:
        result["problems"].append("origin endpoint reports a different preview directory")

    result["ok"] = not result["problems"]
    result["status"] = "ok" if result["ok"] else "stale_or_wrong_worktree"
    return result


def preview_status(
    *,
    directory: str | Path = DEFAULT_DIR,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> dict:
    root = Path(directory).resolve()
    canonical = root / CANONICAL_PREVIEW_FILE
    jsx = root / JSX_VALIDATION_FILE
    html = root / HTML_MIRROR_FILE
    return {
        "primary_surface": "html_dashboard",
        "url": canonical_preview_url(host, port),
        "canonical_url": canonical_preview_url(host, port),
        "html_url": html_mirror_url(host, port),
        "mirror_url": html_mirror_url(host, port),
        "jsx_url": jsx_validation_url(host, port),
        "directory": str(root),
        "preview_file": str(canonical),
        "preview_exists": canonical.is_file(),
        "canonical_file": str(canonical),
        "canonical_exists": canonical.is_file(),
        "html_preview_file": str(html),
        "html_preview_exists": html.is_file(),
        "jsx_preview_file": str(jsx),
        "jsx_preview_exists": jsx.is_file(),
        "server_running": port_is_open(host, port),
    }


class DashboardPreviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == ORIGIN_STATUS_PATH:
            host, port = self.server.server_address[:2]
            body = json.dumps(
                {
                    **preview_status(directory=self.directory, host=host, port=port),
                    "origin_endpoint": ORIGIN_STATUS_PATH,
                    "local_preview": preview_file_metadata(Path(self.directory) / CANONICAL_PREVIEW_FILE),
                },
                indent=2,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def serve_preview(
    *,
    directory: str | Path = DEFAULT_DIR,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> None:
    root = Path(directory).resolve()
    handler = partial(DashboardPreviewHandler, directory=str(root))
    httpd = ThreadingHTTPServer((host, port), handler)
    print(
        json.dumps(
            {
                **preview_status(directory=root, host=host, port=port),
                "origin_endpoint": ORIGIN_STATUS_PATH,
                "serving": True,
            },
            indent=2,
        ),
        flush=True,
    )
    httpd.serve_forever()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Serve or check the local dashboard preview")
    parser.add_argument("--dir", default=str(DEFAULT_DIR), help="Directory containing dashboard_preview.html and optional cockpit_jsx_preview.html")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    parser.add_argument("--check", action="store_true", help="Print status and exit")
    parser.add_argument(
        "--check-origin",
        action="store_true",
        help="Fetch the served preview and fail if it does not match this worktree's preview file",
    )
    args = parser.parse_args(argv)

    status = preview_status(directory=args.dir, host=args.host, port=args.port)
    if args.check_origin:
        origin = served_origin_status(directory=args.dir, host=args.host, port=args.port)
        print(json.dumps({**status, "origin_check": origin}, indent=2))
        return 0 if origin["ok"] else 3
    if args.check:
        print(json.dumps(status, indent=2))
        return 0 if status["preview_exists"] else 2
    if status["server_running"]:
        origin = served_origin_status(directory=args.dir, host=args.host, port=args.port)
        print(json.dumps({**status, "origin_check": origin, "serving": False, "reason": "server already running"}, indent=2))
        return 0
    if not status["preview_exists"]:
        print(json.dumps({**status, "serving": False, "reason": "dashboard preview file missing"}, indent=2))
        return 2
    serve_preview(directory=args.dir, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
