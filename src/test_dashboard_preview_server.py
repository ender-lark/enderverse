import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dashboard_preview_server as server


def _fetcher(mapping):
    def fetch(url):
        value = mapping[url]
        return {"ok": True, "status_code": 200, "url": url, "text": value, "error": ""}

    return fetch


def test_preview_status_reports_file_and_url(tmp_path):
    (tmp_path / "cockpit_jsx_preview.html").write_text("<html>jsx</html>", encoding="utf-8")
    (tmp_path / "dashboard_preview.html").write_text("<html>ok</html>", encoding="utf-8")

    status = server.preview_status(directory=tmp_path, host="127.0.0.1", port=8765)

    assert status["preview_exists"] is True
    assert status["primary_surface"] == "html_dashboard"
    assert status["url"] == "http://127.0.0.1:8765/dashboard_preview.html"
    assert status["canonical_url"] == "http://127.0.0.1:8765/dashboard_preview.html"
    assert status["html_url"] == "http://127.0.0.1:8765/dashboard_preview.html"
    assert status["jsx_url"] == "http://127.0.0.1:8765/cockpit_jsx_preview.html"
    assert status["preview_file"].endswith("dashboard_preview.html")
    assert status["html_preview_exists"] is True
    assert status["jsx_preview_exists"] is True


def test_extract_preview_stamp_prefers_title():
    stamp = server.extract_preview_stamp(
        '<div class="stamp" title="built 2026-06-15 10:32 ET">built short</div>'
    )

    assert stamp == {
        "present": True,
        "title": "built 2026-06-15 10:32 ET",
        "text": "built short",
    }


def test_served_origin_status_passes_when_served_preview_matches(tmp_path, monkeypatch):
    html = '<html><div class="stamp" title="built 2026-06-15 10:32 ET">built</div></html>'
    (tmp_path / "dashboard_preview.html").write_text(html, encoding="utf-8")
    monkeypatch.setattr(server, "port_is_open", lambda *args, **kwargs: True)
    endpoint = {
        "directory": str(tmp_path),
        "local_preview": server.preview_file_metadata(tmp_path / "dashboard_preview.html"),
    }
    fetch = _fetcher(
        {
            "http://127.0.0.1:8765/dashboard_preview.html": html,
            "http://127.0.0.1:8765/__dashboard_origin.json": server.json.dumps(endpoint),
        }
    )

    status = server.served_origin_status(directory=tmp_path, fetcher=fetch)

    assert status["ok"] is True
    assert status["status"] == "ok"
    assert status["problems"] == []


def test_served_origin_status_flags_stale_or_wrong_worktree(tmp_path, monkeypatch):
    local = '<html><div class="stamp" title="built 2026-06-15 10:32 ET">built new</div></html>'
    served = '<html><div class="stamp" title="built 2026-06-15 08:57 ET">built old</div></html>'
    (tmp_path / "dashboard_preview.html").write_text(local, encoding="utf-8")
    monkeypatch.setattr(server, "port_is_open", lambda *args, **kwargs: True)
    fetch = _fetcher(
        {
            "http://127.0.0.1:8765/dashboard_preview.html": served,
            "http://127.0.0.1:8765/__dashboard_origin.json": "{}",
        }
    )

    status = server.served_origin_status(directory=tmp_path, fetcher=fetch)

    assert status["ok"] is False
    assert status["status"] == "stale_or_wrong_worktree"
    assert "does not match this worktree" in " ".join(status["problems"])


def test_port_is_open_detects_listener():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        assert server.port_is_open("127.0.0.1", port)
    finally:
        sock.close()


def test_main_check_fails_when_preview_missing(tmp_path, capsys):
    rc = server.main(["--dir", str(tmp_path), "--check"])

    assert rc == 2
    assert '"preview_exists": false' in capsys.readouterr().out
