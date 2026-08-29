import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CLI = str(Path(__file__).parent.parent / "cli.py")

SCRIPT = """
func page(path) {
    if path == "/" {
        return "<h1>home</h1>"
    }
    return "<h1>other:" + path + "</h1>"
}
serve(PORT, page, 2)
"""


def _get_with_retry(url, attempts=50, delay=0.1):
    last_err = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                return resp.read().decode()
        except (urllib.error.URLError, ConnectionError) as e:
            last_err = e
            time.sleep(delay)
    raise AssertionError(f"server never responded: {last_err}")


def _run_server(tmp_path, engine, port):
    script = tmp_path / "srv.bo"
    script.write_text(SCRIPT.replace("PORT", str(port)))
    proc = subprocess.Popen(
        [sys.executable, CLI, "--engine", engine, str(script)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        home = _get_with_retry(f"http://127.0.0.1:{port}/")
        assert home == "<h1>home</h1>"
        other = _get_with_retry(f"http://127.0.0.1:{port}/about")
        assert other == "<h1>other:/about</h1>"
    finally:
        proc.wait(timeout=5)
    assert proc.returncode == 0


def test_serve_computes_response_per_request_on_vm(tmp_path):
    _run_server(tmp_path, "vm", 8231)


def test_serve_computes_response_per_request_on_tree_walker(tmp_path):
    _run_server(tmp_path, "tree", 8232)
