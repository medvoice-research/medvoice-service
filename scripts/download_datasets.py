#!/usr/bin/env python3
"""Download the simulated patient-physician interview dataset (OSCE respiratory cases).

The dataset was removed from the repository to keep clones small (~1 GB -> ~11 MB).
It is a public, CC0-licensed archive hosted on Springer Nature Figshare:

    A dataset of simulated patient-physician medical interviews
    with a focus on respiratory cases
    https://springernature.figshare.com/collections/A_dataset_of_simulated_patient-physician_medical_interviews_with_a_focus_on_respiratory_cases/5545842/1

Usage:
    python scripts/download_datasets.py            # download + extract + verify
    python scripts/download_datasets.py --dry-run  # print what would happen
    python scripts/download_datasets.py --keep     # keep Data.zip after extraction

Exit codes:
    0 - dataset present and verified
    1 - error (download/extraction/verification failed)
"""

import argparse
import hashlib
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# Figshare direct download for the collection's single file (Data.zip)
FIGSHARE_URL = "https://ndownloader.figshare.com/files/30598530"
ARCHIVE_NAME = "Data.zip"

# Expected SHA-256 of the archive (from the Figshare article record).
ARCHIVE_SHA256 = ""

# Expected contents of the archive, relative to the extracted root.
# (Optional manifest - filled in from the Figshare record on first verified download.)
EXPECTED_DIRS = ["audios", "transcripts"]

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "datasets" / "kaggle-simulated-patient-physician-interviews"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dataset_present() -> bool:
    """Return True if the dataset directory already looks complete."""
    if not DATASET_DIR.is_dir():
        return False
    has_audios = (DATASET_DIR / "audios").is_dir() and any(
        (DATASET_DIR / "audios").glob("*.mp3")
    )
    has_transcripts = (DATASET_DIR / "transcripts").is_dir() and any(
        (DATASET_DIR / "transcripts").glob("*.txt")
    )
    return has_audios and has_transcripts


def download(url: str, dest: Path) -> None:
    """Download url to dest with a simple progress indicator."""
    print(f"Downloading {url}")
    print(f"  -> {dest} (~1 GB, this can take a while)")
    req = urllib.request.Request(url, headers={"User-Agent": "medvoice-dataset-downloader"})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                print(f"\r  {done / 1e6:6.1f} / {total / 1e6:6.1f} MB ({pct:3d}%)", end="", flush=True)
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Only print what would happen")
    parser.add_argument("--keep", action="store_true", help="Keep Data.zip after extraction")
    args = parser.parse_args()

    if dataset_present():
        print(f"Dataset already present at {DATASET_DIR} - nothing to do.")
        return 0

    if args.dry_run:
        print(f"Would download {FIGSHARE_URL} (~1 GB) and extract into {DATASET_DIR}")
        return 0

    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="medvoice-dataset-") as tmp:
        tmp_dir = Path(tmp)
        archive = tmp_dir / ARCHIVE_NAME

        try:
            download(FIGSHARE_URL, archive)
        except Exception as e:
            print(f"ERROR: download failed: {e}", file=sys.stderr)
            return 1

        if ARCHIVE_SHA256:
            actual = sha256_file(archive)
            if actual != ARCHIVE_SHA256:
                print(
                    f"ERROR: checksum mismatch.\n  expected: {ARCHIVE_SHA256}\n  actual:   {actual}",
                    file=sys.stderr,
                )
                return 1
            print("Archive checksum OK")

        print("Extracting...")
        try:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(tmp_dir)
        except zipfile.BadZipFile as e:
            print(f"ERROR: invalid zip archive: {e}", file=sys.stderr)
            return 1

        # Find the extracted content root (handles single-top-level-dir archives)
        extracted = tmp_dir
        entries = [p for p in tmp_dir.iterdir() if p.name != ARCHIVE_NAME]
        if len(entries) == 1 and entries[0].is_dir():
            extracted = entries[0]

        # Move contents into place
        for item in extracted.iterdir():
            dest = DATASET_DIR / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))

    if dataset_present():
        print(f"Dataset ready at {DATASET_DIR}")
        return 0

    print("WARNING: extraction finished but dataset looks incomplete.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
