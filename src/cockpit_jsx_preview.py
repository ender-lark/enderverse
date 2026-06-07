#!/usr/bin/env python3
"""Build a local browser page for the canonical JSX cockpit.

The GitHub Pages dashboard is a generated HTML summary/export surface. During
v1 buildout, operator validation should happen against the canonical JSX
cockpit first, then the HTML mirror should be parity-checked.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPONENT = ROOT / "src" / "rendered" / "conviction_cockpit_v5.jsx"
DEFAULT_OUT_DIR = ROOT / "tmp"
RUNTIME_SOURCE = "cockpit_jsx_preview.runtime.jsx"
RUNTIME_JS = "cockpit_jsx_preview.js"
HTML_FILE = "cockpit_jsx_preview.html"
REACT_IMPORT = 'import React, { useEffect, useState, useMemo } from "react";'
CDN_IMPORTS = (
    'import React, { useEffect, useState, useMemo } from "https://esm.sh/react@18.3.1";\n'
    'import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";'
)
MOUNT_CODE = """

const rootEl = document.getElementById("root");
createRoot(rootEl).render(<ConvictionCockpit />);
"""


def find_npx() -> str:
    candidate = shutil.which("npx.cmd") or shutil.which("npx")
    if not candidate:
        raise RuntimeError("npx is not available; install Node.js to build the JSX preview")
    return candidate


def runtime_source(component_source: str) -> str:
    if REACT_IMPORT not in component_source:
        raise ValueError("React import not found in cockpit component")
    if "export default function ConvictionCockpit" not in component_source:
        raise ValueError("ConvictionCockpit default export not found")
    return component_source.replace(REACT_IMPORT, CDN_IMPORTS, 1) + MOUNT_CODE


def html_source(js_name: str = RUNTIME_JS) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Canonical JSX Conviction Cockpit</title>
<style>
html, body, #root {{ margin:0; min-height:100%; background:#0c0e12; }}
</style>
</head>
<body>
<div id="root"></div>
<script type="module">
import("./{js_name}?v=" + Date.now());
</script>
</body>
</html>
"""


def build_preview(
    *,
    component: str | Path = DEFAULT_COMPONENT,
    out_dir: str | Path = DEFAULT_OUT_DIR,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> dict:
    component_path = Path(component)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    runtime_path = out / RUNTIME_SOURCE
    js_path = out / RUNTIME_JS
    html_path = out / HTML_FILE

    source = component_path.read_text(encoding="utf-8")
    runtime_path.write_text(runtime_source(source), encoding="utf-8")
    html_path.write_text(html_source(RUNTIME_JS), encoding="utf-8")

    subprocess.run(
        [
            find_npx(),
            "--yes",
            "esbuild",
            str(runtime_path),
            "--format=esm",
            "--outfile=" + str(js_path),
            "--loader:.jsx=jsx",
            "--log-level=warning",
        ],
        cwd=ROOT,
        check=True,
    )
    return {
        "url": f"http://{host}:{port}/{HTML_FILE}",
        "html": str(html_path),
        "js": str(js_path),
        "runtime_source": str(runtime_path),
        "component": str(component_path),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build the local canonical JSX cockpit preview page")
    parser.add_argument("--component", default=str(DEFAULT_COMPONENT))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args(argv)
    print(json.dumps(build_preview(component=args.component, out_dir=args.out_dir, host=args.host, port=args.port), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
