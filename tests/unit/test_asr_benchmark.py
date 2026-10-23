"""Offline checks for the benchmark's sampling and published summary."""

import json
import random
from types import SimpleNamespace

from scripts import asr_benchmark as benchmark


def test_fetch_replaces_missing_audio_without_shrinking_sample(tmp_path, monkeypatch):
    missing = random.Random(benchmark.SEED).sample(range(3), 2)[0]
    rows = {
        index: {"audio": None if index == missing else [{"src": "unused"}], "text": f"row {index}", "duration": 1}
        for index in range(3)
    }

    def download(row, stem):
        assert row["audio"]
        return stem.with_suffix(".wav")

    monkeypatch.setattr(benchmark, "ROOT", tmp_path)
    monkeypatch.setattr(benchmark, "OUT_DIR", tmp_path / "benchmarks" / "asr")
    monkeypatch.setattr(benchmark, "MANIFEST", tmp_path / "benchmarks" / "asr" / "manifest.json")
    monkeypatch.setattr(benchmark, "AUDIO_DIR", tmp_path / "datasets" / "vietmed")
    monkeypatch.setattr(benchmark, "_all_labels", lambda: {"DISEASE"})
    monkeypatch.setattr(benchmark, "_num_rows", lambda dataset, split: 3 if dataset == benchmark.VIETMED else 0)
    monkeypatch.setattr(benchmark, "_row_at", lambda dataset, split, index: rows[index])
    monkeypatch.setattr(benchmark, "_download_audio", download)

    benchmark.cmd_fetch(SimpleNamespace(n_vietmed=2, n_ner=0))

    items = json.loads(benchmark.MANIFEST.read_text())["sets"]["vietmed"]
    assert len(items) == 2
    assert missing not in {item["id"] for item in items}


def test_report_uses_latest_result_per_model(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, "OUT_DIR", tmp_path)
    for filename, model, wer in (
        ("2026-10-19-base.json", "base", 0.4),
        ("2026-10-20-base.json", "base", 0.2),
        ("2026-10-20-small.json", "small", 0.1),
    ):
        (tmp_path / filename).write_text(json.dumps({"model": model, "sets": {"vietmed": {"summary": {"wer": wer}}}}))

    benchmark.cmd_report(None)

    report = (tmp_path / "README.md").read_text()
    assert report.count("| base |") == 1
    assert "| small | 0.1 | +50% |" in report
