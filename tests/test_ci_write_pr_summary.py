import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "ci_write_pr_summary", ROOT / "scripts" / "ci_write_pr_summary.py"
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["ci_write_pr_summary"] = _mod
_spec.loader.exec_module(_mod)
render_summary = _mod.render_summary


def test_render_summary_lists_similar_prs(tmp_path):
    data = {
        "meta": {"n_candidates": 3, "snapshot_at": "2026-11-03T00:00:00+00:00", "latency_s": 1.5},
        "findings": [
            {
                "category": "duplicate",
                "confidence": "high",
                "prs": [100, 200],
                "reason": "identical effective patch",
            },
            {
                "category": "merge-conflict",
                "confidence": "high",
                "prs": [100],
                "reason": "conflicts in foo.cc",
            },
        ],
    }
    path = tmp_path / "out.json"
    path.write_text(json.dumps(data))
    text = render_summary(100, data)
    assert "#200" in text
    assert "duplicate" in text
    assert "merge-conflict" in text
    assert "('duplicate'" not in text
