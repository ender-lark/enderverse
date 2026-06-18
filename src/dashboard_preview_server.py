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
import subprocess
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


def _git_text(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return proc.stdout.strip()


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


def feed_file_metadata(path: str | Path | None = None) -> dict:
    feed = Path(path) if path else ROOT / "src" / "latest_cockpit_feed.json"
    if not feed.is_file():
        return {"exists": False, "path": str(feed), "generated_at": "", "sha256": ""}
    raw = feed.read_bytes()
    generated_at = ""
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
        if isinstance(payload, dict):
            generated_at = str(payload.get("generated_at") or "")
    except Exception:
        generated_at = ""
    return {
        "exists": True,
        "path": str(feed),
        "generated_at": generated_at,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def served_checkout_metadata(*, feed_path: str | Path | None = None) -> dict:
    status = _git_text(["status", "--short"])
    feed = feed_file_metadata(feed_path)
    branch = _git_text(["rev-parse", "--abbrev-ref", "HEAD"])
    commit = _git_text(["rev-parse", "--short", "HEAD"])
    return {
        "checkout": str(ROOT),
        "branch": branch,
        "commit": commit,
        "dirty": bool(status),
        "dirty_count": len([line for line in status.splitlines() if line.strip()]),
        "feed": feed,
        "text": (
            f"checkout={ROOT} | branch={branch or 'unknown'} | "
            f"commit={commit or 'unknown'} | "
            f"feed={feed.get('generated_at') or 'missing'} | "
            f"feed_sha256={(feed.get('sha256') or '')[:16]}"
        ),
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
        "local_server_health": status.get("server_health") or {},
        "server_health": {},
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
    if result["server_report"]:
        result["server_health"] = result["server_report"].get("server_health") or result["server_health"]
        if not result["server_health"]:
            result["problems"].append("origin endpoint missing server health metadata")

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
        "server_health": served_checkout_metadata(),
    }


DISPOSITION_ENDPOINT = "/td/disposition"
NOTE_ENDPOINT = "/td/note"
NOTES_PATH = ROOT / "src" / "card_notes.jsonl"
_MAX_POST_BYTES = 16_384


def append_disposition_from_payload(data: dict, *, path=None) -> dict:
    """Persist a TODAY—DECIDE rail tap into the append-only disposition spine.

    This is the 'fully automatic' write-back: a tap on the served dashboard lands
    here (same-origin POST) and is appended to ``dispositions.jsonl`` directly — no
    copy-paste. Verbs are validated against the spine; a PASS with no operator reason
    gets a non-empty placeholder so the append never silently fails."""
    import disposition_log

    card_id = str((data or {}).get("card_id") or "").strip()
    ticker = str((data or {}).get("ticker") or "").strip()
    verb = str((data or {}).get("verb") or "").strip().upper()
    et_date = str((data or {}).get("et_date") or "").strip()
    reason = (data or {}).get("reason")
    source = str((data or {}).get("source") or "dashboard").strip() or "dashboard"
    if not card_id:
        raise ValueError("card_id is required")
    if verb not in disposition_log.VALID_VERBS:
        raise ValueError(f"unsupported verb: {verb!r}")
    if verb in disposition_log.REASON_REQUIRED_VERBS and not (reason and str(reason).strip()):
        reason = "dashboard one-tap (no reason given)"
    target = path if path is not None else disposition_log.DISPOSITIONS_PATH
    return disposition_log.append_disposition(
        et_date, card_id, ticker, verb, reason, source=source, path=target
    )


def append_note_from_payload(data: dict, *, path=None) -> dict:
    """Persist a per-card ask/comment into an append-only notes log (same spine
    family as dispositions). card_id-scoped so chat can resolve the exact card."""
    import datetime as _dt

    card_id = str((data or {}).get("card_id") or "").strip()
    note = str((data or {}).get("note") or "").strip()
    if not card_id or not note:
        raise ValueError("card_id and note are required")
    row = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "card_id": card_id,
        "ticker": str((data or {}).get("ticker") or "").strip().upper(),
        "note": note[:2000],
        "source": "dashboard",
    }
    out = Path(path) if path is not None else NOTES_PATH
    parent = out.parent
    if parent and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
    with open(out, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
    return row


class DashboardPreviewHandler(SimpleHTTPRequestHandler):
    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path not in (DISPOSITION_ENDPOINT, NOTE_ENDPOINT):
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0 or length > _MAX_POST_BYTES:
            self._send_json(400, {"ok": False, "error": "missing or oversized body"})
            return
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("body must be a JSON object")
        except Exception:
            self._send_json(400, {"ok": False, "error": "invalid JSON body"})
            return
        try:
            if path == DISPOSITION_ENDPOINT:
                row = append_disposition_from_payload(data)
            else:
                row = append_note_from_payload(data)
            self._send_json(200, {"ok": True, "row": row})
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
        except Exception:
            self._send_json(500, {"ok": False, "error": "server error"})

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
