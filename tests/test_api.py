"""回归触发 API 自测（离线：不跑真实 pytest，仅打桩 RunManager 验证协议层）。"""
from __future__ import annotations

import io
import json
import threading
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

import pytest

from apw.api import (
    RunManager,
    RunRequest,
    RunState,
    _parse_request,
    build_report_zip,
    make_handler,
    resolve_token,
)


class TestToken:
    def test_cli_token_wins(self, monkeypatch):
        monkeypatch.setenv("APW_API_TOKEN", "from-env")
        assert resolve_token("from-cli") == "from-cli"

    def test_env_beats_secrets(self, monkeypatch):
        monkeypatch.setenv("APW_API_TOKEN", "from-env")
        assert resolve_token() == "from-env"

    def test_secrets_file_used_when_no_cli_or_env(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APW_API_TOKEN", raising=False)
        monkeypatch.setattr("apw.api.repo_root", lambda: tmp_path)
        (tmp_path / "configs").mkdir()
        (tmp_path / "configs" / "secrets.local.yaml").write_text(
            'api:\n  token: "from-secrets"\n', encoding="utf-8"
        )
        assert resolve_token() == "from-secrets"

    def test_missing_everything_yields_empty(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APW_API_TOKEN", raising=False)
        monkeypatch.setattr("apw.api.repo_root", lambda: tmp_path)
        assert resolve_token() == ""


class TestRequest:
    def test_to_pytest_args_basic(self):
        args = RunRequest(env="test", targets=["flows"]).to_pytest_args()
        assert args == ["flows", "--apw-env", "test", "--apw-flows-dir", "flows"]

    def test_to_pytest_args_full(self):
        args = RunRequest(
            env="desktop",
            targets=["flows/desktop_chat_smoke.yaml"],
            tags=["smoke", "desktop"],
            flows_dir="flows",
            headed=True,
            slowmo=250,
            extra_args=["-x"],
        ).to_pytest_args()
        assert args[:2] == ["flows/desktop_chat_smoke.yaml", "--apw-env"]
        assert "--apw-headed" in args
        assert args[args.index("--apw-slowmo") + 1] == "250"
        assert args[args.index("-m") + 1] == "smoke or desktop"
        assert args[-1] == "-x"

    def test_parse_request_lenient(self):
        req = _parse_request({"env": "test", "targets": "flows", "unknown": 1})
        assert req.targets == ["flows"]
        assert req.env == "test"

    def test_parse_request_defaults(self):
        req = _parse_request({})
        assert req.env == "fixture" and req.targets == ["flows"]
        assert req.callback_url == ""


class TestArtifacts:
    def test_zip_contains_run_tree(self, tmp_path):
        run_dir = tmp_path / "20261014-101010-ab12"
        run_dir.mkdir()
        (run_dir / "run-summary.json").write_text('{"total": 1}', encoding="utf-8")
        (run_dir / "report.html").write_text("<html>ok</html>", encoding="utf-8")
        (run_dir / "flow-a-step00.png").write_bytes(b"\x89PNG")
        blob = build_report_zip(run_dir)
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = set(zf.namelist())
        assert names == {
            "20261014-101010-ab12/run-summary.json",
            "20261014-101010-ab12/report.html",
            "20261014-101010-ab12/flow-a-step00.png",
        }

    def test_zip_skips_pyc(self, tmp_path):
        run_dir = tmp_path / "20261014-101010-ab12"
        (run_dir / "__pycache__").mkdir(parents=True)
        (run_dir / "__pycache__" / "x.pyc").write_bytes(b"\x00")
        (run_dir / "run-summary.json").write_text("{}", encoding="utf-8")
        blob = build_report_zip(run_dir)
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            assert all(not n.endswith(".pyc") for n in zf.namelist())

    def test_zip_missing_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            build_report_zip(tmp_path / "absent")


class TestSnapshot:
    def test_snapshot_reads_summary(self, tmp_path):
        run_dir = tmp_path / "run1"
        run_dir.mkdir()
        (run_dir / "run-summary.json").write_text(
            json.dumps(
                {
                    "total": 2,
                    "passed": 1,
                    "failed": 1,
                    "skipped": 0,
                    "flows": [
                        {"flow_id": "a", "name": "甲", "status": "passed"},
                        {"flow_id": "b", "name": "乙", "status": "failed"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        state = RunState(run_id="r1", request=RunRequest(), status="finished", run_dir=str(run_dir))
        snap = state.snapshot("http://127.0.0.1:18787")
        assert snap["summary"] == {"total": 2, "passed": 1, "failed": 1, "skipped": 0}
        assert snap["failed_flows"][0]["flow_id"] == "b"
        assert snap["report_zip"].endswith("/runs/r1/report.zip")

    def test_snapshot_without_summary(self):
        snap = RunState(run_id="r2", request=RunRequest()).snapshot()
        assert "summary" not in snap and snap["status"] == "queued"


class _StubManager(RunManager):
    """不启真实执行线程的桩：直接给定状态与产物。"""

    def __init__(self, run_dir: str = "") -> None:  # noqa: D107 - 测试桩
        self.runs = {}
        self.order = []
        self._lock = threading.Lock()
        self._run_dir = run_dir

    def submit(self, req: RunRequest) -> RunState:
        state = RunState(run_id="stub1", request=req, status="finished", run_dir=self._run_dir)
        self.runs["stub1"] = state
        self.order.append("stub1")
        return state


@pytest.fixture
def api_server(tmp_path):
    run_dir = tmp_path / "20261014-101010-ab12"
    run_dir.mkdir()
    (run_dir / "run-summary.json").write_text('{"total": 0}', encoding="utf-8")
    manager = _StubManager(str(run_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(manager, "secret"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base
    server.shutdown()
    thread.join(timeout=5)


def _get(url: str, token: str = "secret"):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(req, timeout=10)


class TestHttp:
    def test_health_needs_no_auth(self, api_server):
        with _get(f"{api_server}/health", token="") as resp:
            assert json.load(resp)["status"] == "ok"

    def test_unauthorized_without_token(self, api_server):
        with pytest.raises(urllib.error.HTTPError) as exc:
            _get(f"{api_server}/runs", token="")
        assert exc.value.code == 401

    def test_post_run_returns_202(self, api_server):
        req = urllib.request.Request(
            f"{api_server}/runs",
            data=json.dumps({"env": "test"}).encode(),
            headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status == 202
            body = json.load(resp)
        assert body["run_id"] == "stub1" and body["report_zip"].endswith("report.zip")

    def test_get_run_and_zip(self, api_server):
        # 先触发一轮（桩会立即置 finished），再查状态与取包
        req = urllib.request.Request(
            f"{api_server}/runs",
            data=b"{}",
            headers={"Authorization": "Bearer secret"},
        )
        urllib.request.urlopen(req, timeout=10).close()
        with _get(f"{api_server}/runs/stub1") as resp:
            assert json.load(resp)["run_id"] == "stub1"
        with _get(f"{api_server}/runs/stub1/report.zip") as resp:
            assert resp.headers["Content-Type"] == "application/zip"
            with zipfile.ZipFile(io.BytesIO(resp.read())) as zf:
                assert any(n.endswith("run-summary.json") for n in zf.namelist())

    def test_unknown_run_404(self, api_server):
        with pytest.raises(urllib.error.HTTPError) as exc:
            _get(f"{api_server}/runs/nope")
        assert exc.value.code == 404

    def test_invalid_json_400(self, api_server):
        req = urllib.request.Request(
            f"{api_server}/runs",
            data=b"{not json",
            headers={"Authorization": "Bearer secret"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=10)
        assert exc.value.code == 400
