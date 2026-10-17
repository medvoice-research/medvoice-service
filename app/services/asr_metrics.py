"""Text metrics for the Vietnamese ASR benchmark (scripts/asr_benchmark.py).

Tone marks are meaning in Vietnamese ("má" mother vs "mà" but), so normalization keeps
them: Unicode NFC, lowercase, punctuation stripped, whitespace collapsed. VietMed references
spell numbers out ("năm mươi lăm"), while Whisper often emits digits, so digits are spelled
the same way before scoring.
"""

import re
import unicodedata

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_NUMBER = re.compile(r"\d+")
_DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_GROUPS = ["", "nghìn", "triệu", "tỷ"]


def _three(n: int, full: bool) -> list[str]:
    """Read 0-999; ``full`` forces "không trăm"/"linh" for non-leading groups."""
    h, t, u = n // 100, n // 10 % 10, n % 10
    out = []
    if h or full:
        out += [_DIGITS[h], "trăm"]
    if t == 0:
        if u and out:
            out.append("linh")
    elif t == 1:
        out.append("mười")
    else:
        out += [_DIGITS[t], "mươi"]
    if u:
        out.append("mốt" if u == 1 and t >= 2 else "lăm" if u == 5 and t >= 1 else _DIGITS[u])
    return out


def spell_number(n: int) -> str:
    # ponytail: integers only, up to 999 tỷ; decimals ("1,5") read as two numbers.
    if n == 0:
        return _DIGITS[0]
    groups = []
    while n:
        groups.append(n % 1000)
        n //= 1000
    words = []
    for i in range(len(groups) - 1, -1, -1):
        if groups[i]:
            words += _three(groups[i], full=i < len(groups) - 1) + ([_GROUPS[i]] if _GROUPS[i] else [])
    return " ".join(words)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower().replace("%", " phần trăm ")
    text = _NUMBER.sub(lambda m: f" {spell_number(int(m.group()))} " if len(m.group()) <= 12 else m.group(), text)
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
