import json
import pathlib

from fastapi.testclient import TestClient

from app.batch_runner import run_folder
from app.main import app
from app.mock_platforms import reset_state


def test_batch_runner_end_to_end(tmp_path):
    reset_state()
    code = run_folder(
        TestClient(app),
        pathlib.Path("batch_inputs"),
        tmp_path,
        token=None,
        poll_s=0,
        timeout_s=10,
    )
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert code == 0, summary
    assert summary["failed"] == 0 and summary["total"] >= 8
