"""Vietnamese ASR benchmark (spec: docs/superpowers/specs/2026-10-17-vietnamese-asr-accuracy-design.md).

    python scripts/asr_benchmark.py fetch                     # seeded VietMed / VietMed-NER subsets
    python scripts/asr_benchmark.py run --model base          # one model per process
    python scripts/asr_benchmark.py run --model mad1999/pho-whisper-medium-ct2 --hotwords data/vocab/vi_medical.txt --tag vocab
    python scripts/asr_benchmark.py vocab                     # build data/vocab/vi_medical.txt from NER *train*
    python scripts/asr_benchmark.py report                    # markdown table -> benchmarks/asr/README.md

Data comes from the HF datasets-server rows API with stdlib only: the repo's own
``datasets/`` directory shadows the ``datasets`` package, and pyarrow is not installed.
"""

import argparse
import json
import random
import resource
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.asr_metrics import cer, entity_spans, term_hits, wer  # noqa: E402

SEED = 17
AUDIO_DIR = ROOT / "datasets" / "vietmed"
OUT_DIR = ROOT / "benchmarks" / "asr"
MANIFEST = OUT_DIR / "manifest.json"
VOCAB = ROOT / "data" / "vocab" / "vi_medical.txt"
ROWS_API = "https://datasets-server.huggingface.co/rows"
# Non-clinical VietMed-NER labels; every other label counts as a medical term.
NON_CLINICAL = {"DATETIME", "UNITCALIBRATOR", "PERSON", "LOCATION", "ORGANIZATION", "GENDER", "AGE", "OCCUPATION"}
VIETMED, NER = "leduckhai/VietMed", "leduckhai/VietMed-NER"


def _fetch(url: str, retries: int = 8) -> bytes:
    """GET with backoff; the datasets-server rate-limits (429) bursts of requests."""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if attempt == retries - 1 or (e.code != 429 and e.code < 500):
                raise
            time.sleep(float(e.headers.get("Retry-After") or min(60, 5 * 2**attempt)))
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
            time.sleep(5 * (attempt + 1))


def _get_json(url: str) -> dict:
    return json.loads(_fetch(url))


def _rows(dataset: str, split: str, offset: int, length: int = 100) -> list[dict]:
    q = urllib.parse.urlencode(
        {"dataset": dataset, "config": "default", "split": split, "offset": offset, "length": length}
    )
    return [r["row"] for r in _get_json(f"{ROWS_API}?{q}")["rows"]]


_PAGES: dict[tuple, list[dict]] = {}


def _row_at(dataset: str, split: str, idx: int) -> dict:
    """One row, fetched as part of a cached 100-row page (35 requests per split, not 3500)."""
    key = (dataset, split, idx // 100)
    if key not in _PAGES:
        _PAGES[key] = _rows(dataset, split, key[2] * 100)
    return _PAGES[key][idx % 100]


def _num_rows(dataset: str, split: str) -> int:
    info = _get_json(f"https://datasets-server.huggingface.co/info?dataset={urllib.parse.quote(dataset)}")
    return info["dataset_info"]["default"]["splits"][split]["num_examples"]


def _download_audio(row: dict, dest_stem: Path) -> Path:
    src = row["audio"][0]["src"]
    ext = ".wav" if "wav" in row["audio"][0].get("type", "") else ".mp3"
    dest = dest_stem.with_suffix(ext)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(_fetch(src))
    return dest


def _all_labels() -> set[str]:
    """Entity label names seen in the first 400 NER test rows (the set is small and fixed)."""
    names = set()
    for off in range(0, 400, 100):
        for row in _rows(NER, "test", off, 100):
            names |= {lbl.partition("-")[2] for lbl in row["labels"] if "-" in lbl}
    return names


def cmd_fetch(args) -> None:
    rng = random.Random(SEED)
    kept = sorted(_all_labels() - NON_CLINICAL)
    print("medical labels kept:", kept)

    vm_idx = sorted(rng.sample(range(_num_rows(VIETMED, "test")), args.n_vietmed))
    vietmed = []
    for i, idx in enumerate(vm_idx):
        row = _row_at(VIETMED, "test", idx)
        path = _download_audio(row, AUDIO_DIR / "vietmed" / str(idx))
        vietmed.append(
            {"id": idx, "path": str(path.relative_to(ROOT)), "text": row["text"], "duration": row["duration"]}
        )
        print(f"\rvietmed {i + 1}/{len(vm_idx)}", end="", flush=True)
    print()

    # NER subset: only utterances with at least one medical entity carry term-recall signal.
    ner_total = _num_rows(NER, "test")
    order = list(range(ner_total))
    rng.shuffle(order)
    ner = []
    for idx in order:
        if len(ner) == args.n_ner:
            break
        row = _row_at(NER, "test", idx)
        terms = entity_spans(row["words"], row["labels"], set(kept))
        # The rows API returns audio=None for some rows; they carry no usable sample.
        if not terms or not row.get("audio"):
            continue
        path = _download_audio(row, AUDIO_DIR / "ner" / str(idx))
        ner.append(
            {
                "id": idx,
                "path": str(path.relative_to(ROOT)),
                "text": row["text"],
                "duration": row["duration"],
                "terms": terms,
            }
        )
        print(f"\rner {len(ner)}/{args.n_ner}", end="", flush=True)
    print()

    clips = []
    for audio in sorted((ROOT / "datasets" / "audios" / "vn").glob("*.mp3")):
        ref = ROOT / "datasets" / "transcripts" / "vn" / f"{audio.stem}.txt"
        if ref.exists():
            clips.append(
                {"id": audio.stem, "path": str(audio.relative_to(ROOT)), "text": ref.read_text(encoding="utf-8")}
            )
        else:
            print(f"warning: no reference for {audio.name} ({ref.relative_to(ROOT)}); clip skipped")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(
            {"seed": SEED, "kept_labels": kept, "sets": {"vietmed": vietmed, "ner": ner, "clips": clips}},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"wrote {MANIFEST.relative_to(ROOT)}: vietmed={len(vietmed)} ner={len(ner)} clips={len(clips)}")


def _prompt_terms(path: Path, max_chars: int) -> str:
    """Top terms (file is frequency-ordered) that fit faster-whisper's ~224-token prompt budget."""
    out, size = [], 0
    for term in path.read_text(encoding="utf-8").split("\n"):
        if term and size + len(term) + 2 <= max_chars:
            out.append(term)
            size += len(term) + 2
    return ", ".join(out)


def _seconds(audio) -> float:
    return len(audio) / 16000  # whisperx.load_audio resamples to 16 kHz mono


def cmd_run(args) -> None:
    from whisperx import load_audio

    import app.whisperx_services as ws
    from app.schemas import ASROptions, VADOptions, WhisperModel
    from app.services.recording_pipeline import _defaults

    model = WhisperModel(args.model)
    asr = ASROptions(**_defaults(ASROptions)).model_dump()
    prompt = None
    if args.hotwords:
        prompt = _prompt_terms(Path(args.hotwords), args.prompt_chars)
        asr["hotwords"] = prompt
        asr["initial_prompt"] = prompt
    vad = VADOptions(**_defaults(VADOptions)).model_dump()
    # The model cache key ignores asr_options; never reuse a model built with other hotwords.
    ws._transcription_model_cache.clear()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    result = {
        "model": model.value,
        "tag": args.tag,
        "date": date.today().isoformat(),
        "device": "cpu",
        "compute_type": "int8",
        "threads": args.threads,
        "cpu": _cpu_name(),
        "prompt": prompt,
        "sets": {},
    }

    def transcribe(audio):
        return ws.transcribe_with_whisper(
            audio=audio,
            task="transcribe",
            asr_options=asr,
            vad_options=vad,
            language="vi",
            model=model,
            device="cpu",
            compute_type="int8",
            threads=args.threads,
        )

    # Untimed warm-up: the first call downloads/loads the model, which is not inference cost.
    transcribe(load_audio(str(ROOT / manifest["sets"]["vietmed"][0]["path"])))

    for set_name, items in manifest["sets"].items():
        items = items[: args.limit] if args.limit else items
        if not items:
            continue
        per, tot = [], Counter()
        for item in items:
            audio = load_audio(str(ROOT / item["path"]))
            t0 = time.perf_counter()
            out = transcribe(audio)
            elapsed = time.perf_counter() - t0
            hyp = " ".join(s["text"].strip() for s in out.get("segments", []))
            we, wn = wer(item["text"], hyp)
            ce, cn = cer(item["text"], hyp)
            row = {
                "id": item["id"],
                "ref": item["text"],
                "hyp": hyp,
                "word_edits": we,
                "words": wn,
                "time": round(elapsed, 3),
            }
            tot.update(word_edits=we, words=wn, char_edits=ce, chars=cn, time=elapsed, audio=_seconds(audio))
            if "terms" in item:
                hits = term_hits(item["terms"], hyp)
                row.update(terms=item["terms"], term_hits=hits)
                tot.update(term_hits=hits, terms=len(item["terms"]))
            per.append(row)
            print(f"\r{set_name} {len(per)}/{len(items)}", end="", flush=True)
        print()
        summary = {
            "n": len(per),
            "audio_seconds": round(tot["audio"], 1),
            "wer": round(tot["word_edits"] / max(tot["words"], 1), 4),
            "cer": round(tot["char_edits"] / max(tot["chars"], 1), 4),
            "rtf": round(tot["time"] / max(tot["audio"], 1e-9), 4),
        }
        if tot["terms"]:
            summary["term_recall"] = round(tot["term_hits"] / tot["terms"], 4)
        result["sets"][set_name] = {"summary": summary, "items": per}
        print(set_name, summary)
    # ru_maxrss is bytes on macOS, KiB on Linux.
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result["peak_rss_mb"] = round(rss / (1024 * 1024 if sys.platform == "darwin" else 1024))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = model.value.replace("/", "__") + (f"-{args.tag}" if args.tag else "") + ("-limit" if args.limit else "")
    out_path = OUT_DIR / f"{result['date']}-{slug}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out_path.relative_to(ROOT)} (peak RSS {result['peak_rss_mb']} MB)")


def _cpu_name() -> str:
    import platform
    import subprocess

    if sys.platform == "darwin":
        return subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
        ).stdout.strip()
    return platform.processor() or platform.machine()


def cmd_vocab(args) -> None:
    """Frequency-ordered medical terms from VietMed-NER *train* (never test: no leakage)."""
    kept = set(json.loads(MANIFEST.read_text(encoding="utf-8"))["kept_labels"])
    counts = Counter()
    total = _num_rows(NER, "train")
    for off in range(0, total, 100):
        for row in _rows(NER, "train", off, 100):
            counts.update(t.lower() for t in entity_spans(row["words"], row["labels"], kept))
        print(f"\rtrain {min(off + 100, total)}/{total}", end="", flush=True)
    print()
    terms = [t for t, c in counts.most_common() if c >= args.min_count and len(t) > 1]
    VOCAB.parent.mkdir(parents=True, exist_ok=True)
    VOCAB.write_text("\n".join(terms) + "\n", encoding="utf-8")
    print(f"wrote {VOCAB.relative_to(ROOT)}: {len(terms)} terms (min count {args.min_count})")


def cmd_report(args) -> None:
    rows = []
    for f in sorted(OUT_DIR.glob("*.json")):
        if f.name == "manifest.json" or f.stem.endswith("-limit"):
            continue
        r = json.loads(f.read_text(encoding="utf-8"))
        vm, ner = r["sets"].get("vietmed", {}).get("summary", {}), r["sets"].get("ner", {}).get("summary", {})
        rows.append((r["model"] + (f" ({r['tag']})" if r.get("tag") else ""), vm, ner, r.get("peak_rss_mb")))
    base = next((vm.get("wer") for name, vm, _, _ in rows if name == "base"), None)
    lines = [
        "| Model | VietMed WER | ΔWER vs base | VietMed CER | NER WER | Term recall | RTF (VietMed) | Peak RSS MB |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, vm, ner, rss in sorted(rows, key=lambda x: x[1].get("wer", 9)):
        delta = f"{(base - vm['wer']) / base:+.0%}" if base and "wer" in vm else "—"
        lines.append(
            f"| {name} | {vm.get('wer', '—')} | {delta} | {vm.get('cer', '—')} | {ner.get('wer', '—')} | "
            f"{ner.get('term_recall', '—')} | {vm.get('rtf', '—')} | {rss} |"
        )
    table = "\n".join(lines)
    print(table)
    readme = OUT_DIR / "README.md"
    header = (
        readme.read_text(encoding="utf-8").split("<!-- results -->")[0]
        if readme.exists()
        else "# ASR benchmark results\n\n"
    )
    readme.write_text(f"{header}<!-- results -->\n{table}\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--n-vietmed", type=int, default=300)
    f.add_argument("--n-ner", type=int, default=200)
    r = sub.add_parser("run")
    r.add_argument("--model", required=True)
    r.add_argument("--hotwords")
    r.add_argument("--prompt-chars", type=int, default=400)
    r.add_argument("--tag")
    r.add_argument("--limit", type=int)
    r.add_argument("--threads", type=int, default=8)
    v = sub.add_parser("vocab")
    v.add_argument("--min-count", type=int, default=3)
    sub.add_parser("report")
    args = p.parse_args()
    {"fetch": cmd_fetch, "run": cmd_run, "vocab": cmd_vocab, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
