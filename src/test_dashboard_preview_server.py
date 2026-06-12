import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dashboard_preview_server as server


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
