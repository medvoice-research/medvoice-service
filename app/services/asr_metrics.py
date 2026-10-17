"""Text metrics for the Vietnamese ASR benchmark (scripts/asr_benchmark.py).

Tone marks are meaning in Vietnamese ("má" mother vs "mà" but), so normalization keeps
them: Unicode NFC, lowercase, punctuation stripped, whitespace collapsed.
"""

import re
import unicodedata

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    return " ".join(_PUNCT.sub(" ", text).split())


def _edits(ref: list, hyp: list) -> int:
    """Levenshtein distance over token lists (two-row DP)."""
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1]


def wer(ref: str, hyp: str) -> tuple[int, int]:
    """(word edits, reference word count) — sum both over a corpus, then divide."""
    r, h = normalize(ref).split(), normalize(hyp).split()
    return _edits(r, h), len(r)


def cer(ref: str, hyp: str) -> tuple[int, int]:
    """(character edits, reference character count), spaces excluded."""
    r, h = list(normalize(ref).replace(" ", "")), list(normalize(hyp).replace(" ", ""))
    return _edits(r, h), len(r)


def entity_spans(words: list[str], labels: list[str], keep: set[str]) -> list[str]:
    """Join BIO-tagged runs (B-X, I-X...) into entity strings, keeping labels in ``keep``."""
    spans, cur, cur_label = [], [], None
    for word, label in zip(words, labels):
        tag, _, name = label.partition("-")
        if tag == "I" and cur and name == cur_label:
            cur.append(word)
            continue
        if cur and cur_label in keep:
            spans.append(" ".join(cur))
        cur, cur_label = ([word], name) if tag in ("B", "I") else ([], None)
    if cur and cur_label in keep:
        spans.append(" ".join(cur))
    return spans


def term_hits(terms: list[str], hyp: str) -> int:
    """How many reference terms appear as whole-word sequences in the hypothesis."""
    padded = f" {normalize(hyp)} "
    return sum(f" {normalize(t)} " in padded for t in terms)
