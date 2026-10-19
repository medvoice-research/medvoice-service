"""Medical-term guard: catch misheard medicine, symptom, disease and test names.

ASR turns unfamiliar drug names into ordinary words ("metformin" -> "men hormone").
A text-only model can't repair that: asked to choose, TypeSafe Jev picked metoprolol
or amlodipine over metformin because "huyết áp" (blood pressure) came next. So each
step uses the evidence it actually has:

1. Whisper (sound): words the ASR model itself scores as unlikely become suspect spans.
2. SemIf (meaning, local model, scripts/semif_server.py): is the suspect span a
   misheard medicine, symptom, disease or test name?
3. Whisper again (sound): rescore the segment with each sound-alike lexicon term in
   place of the span. Replace it only when one term is nearly as likely as what was
   decoded and clearly beats every other term; otherwise flag it for the clinician.

Lexicon: data/vocab/vi_medical.txt (VietMed-NER train terms) and
data/vocab/drugs_who_eml.txt (WHO Model List of Essential Medicines, via Wikipedia).
"""

import difflib
import json
import math
import re
import unicodedata
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from ctranslate2 import StorageView

from app.config import Config
from app.logger import logger

VOCAB_DIR = Path(__file__).resolve().parents[2] / "data" / "vocab"
SAMPLE_RATE = 16000
N_FRAMES = 3000  # Whisper's 30 s input window, in mel frames


def _key(text: str) -> str:
    """Spelling key that ignores tone marks, case, spaces and punctuation."""
    text = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in text if unicodedata.category(c) != "Mn"))


@lru_cache(maxsize=None)
def _lexicon() -> Dict[str, str]:
    terms: Dict[str, str] = {}
    for name in ("vi_medical.txt", "drugs_who_eml.txt"):
        for line in (VOCAB_DIR / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                terms.setdefault(_key(line), line.strip())
    return terms


class _SegmentScorer:
    """Whisper forced scoring of candidate texts against one segment's audio."""

    def __init__(self, whisper, audio: np.ndarray, start: float, end: float, language: str):
        self.whisper = whisper
        self.tokenizer = whisper.hf_tokenizer
        feats = whisper.feature_extractor(audio[int(start * SAMPLE_RATE) : int(end * SAMPLE_RATE)])[:, :N_FRAMES]
        self.frames = feats.shape[-1]
        feats = np.pad(feats, ((0, 0), (0, N_FRAMES - self.frames)))[None].astype(np.float32)
        self.encoded = np.asarray(whisper.model.encode(StorageView.from_array(feats)))
        self.sot = [
            self.tokenizer.token_to_id(t)
            for t in ("<|startoftranscript|>", f"<|{language}|>", "<|transcribe|>", "<|notimestamps|>")
        ]

    def token_probs(self, texts: List[str]):
        ids = [self.tokenizer.encode(" " + t, add_special_tokens=False).ids for t in texts]
        encoded = StorageView.from_array(np.ascontiguousarray(np.repeat(self.encoded, len(texts), axis=0)))
        results = self.whisper.model.align(encoded, self.sot, ids, [self.frames] * len(texts))
        return ids, [r.text_token_probs for r in results]

    def logprobs(self, texts: List[str]) -> List[float]:
        return [sum(math.log(max(p, 1e-12)) for p in probs) for probs in self.token_probs(texts)[1]]

    def word_probs(self, text: str) -> List[float]:
        """Lowest token probability per word; byte-level BPE marks word starts with 'Ġ'."""
        ids, probs = self.token_probs([text])
        words: List[float] = []
        for token_id, p in zip(ids[0], probs[0]):
            if self.tokenizer.id_to_token(token_id).startswith("Ġ"):
                words.append(p)
            elif words:
                words[-1] = min(words[-1], p)
        return words


def _low_runs(word_probs: List[float], threshold: float) -> List[tuple]:
    """Runs of consecutive low-probability words, as (start, end) word indices.

    The first word is skipped: Whisper scores the first token without context, so it
    is low even when right.
    """
    runs, start = [], None
    for i, p in enumerate(word_probs + [1.0]):
        low = i > 0 and p < threshold
        if low and start is None:
            start = i
        elif not low and start is not None:
            runs.append((start, i))
            start = None
    return runs


def _semif(state: str, phrases: List[str]) -> tuple:
    rows = [
        {
            "id": str(i),
            "question": (
                f"The phrase '{phrase}' in this speech-recognition transcript of a clinical dictation: "
                "is it a misheard name of a medicine, symptom, disease or medical test?"
            ),
            "options": [
                {"id": "misheard", "description": "Yes, a medical name the speech recognizer got wrong."},
                {"id": "fine", "description": "No, ordinary words or a correctly transcribed term."},
            ],
        }
        for i, phrase in enumerate(phrases)
    ]
    request = urllib.request.Request(
        f"{Config.SEMIF_URL}/decide",
        data=json.dumps({"state": state, "rows": rows}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=Config.TERM_GUARD_TIMEOUT_SECONDS) as response:
        body = json.loads(response.read())
    return body["model"], [body["answers"][str(i)]["misheard"] for i in range(len(phrases))]


def guard_terms(segments: List[Dict[str, Any]], audio: np.ndarray, whisper, language: str) -> Dict[str, Any]:
    """Check suspect words in place: corrects ``segments[*]["text"]`` and returns the review.

    ``whisper`` is the faster-whisper model that produced the segments.
    """
    suspects = []  # (segment index, words, start, end, scorer)
    for index, segment in enumerate(segments):
        words = segment.get("text", "").split()
        if len(words) < 2:
            continue
        scorer = _SegmentScorer(whisper, audio, segment["start"], segment["end"], language)
        word_probs = scorer.word_probs(" ".join(words))
        if len(word_probs) != len(words):
            logger.warning(f"Term guard: token/word mismatch in segment {index}, skipped")
            continue
        for start, end in _low_runs(word_probs, Config.TERM_GUARD_LOW_WORD_PROB):
            suspects.append((index, words, start, end, scorer))
    if not suspects:
        return {"status": "ok", "terms": []}

    state = " ".join(s.get("text", "").strip() for s in segments)
    phrases = [" ".join(words[start:end]) for _, words, start, end, _ in suspects]
    try:
        model, p_misheard = _semif(state, phrases)
    except Exception as e:
        logger.warning(f"Term guard: SemIf unavailable ({e}); {len(suspects)} suspect span(s) unchecked")
        return {"status": "unavailable", "terms": []}

    lexicon = _lexicon()
    terms, replacements = [], {}  # replacements: segment index -> [(start, end, term)]
    for (index, words, start, end, scorer), phrase, p in zip(suspects, phrases, p_misheard):
        if p < Config.TERM_GUARD_FLAG_PROB:
            continue
        keys = difflib.get_close_matches(
            _key(phrase), [k for k in lexicon if k != _key(phrase)], n=Config.TERM_GUARD_CANDIDATES, cutoff=0.5
        )
        candidates = [lexicon[k] for k in keys]
        original = " ".join(words)
        scores = scorer.logprobs([original] + [" ".join(words[:start] + [c] + words[end:]) for c in candidates])
        ranked = sorted(zip(candidates, scores[1:]), key=lambda c: -c[1])
        best_gap = ranked[0][1] - ranked[1][1] if len(ranked) > 1 else math.inf
        fix = bool(ranked) and scores[0] - ranked[0][1] <= Config.TERM_GUARD_MAX_LOSS and best_gap >= Config.TERM_GUARD_MIN_GAP
        if fix:
            replacements.setdefault(index, []).append((start, end, ranked[0][0]))
        terms.append(
            {
                "original": phrase,
                "replacement": ranked[0][0] if fix else None,
                "action": "corrected" if fix else "flagged",
                "p_misheard": round(p, 3),
                # log-probability of the segment with each term, relative to what was decoded
                "suggestions": [{"term": c, "score": round(s - scores[0], 2)} for c, s in ranked],
                "start": segments[index]["start"],
                "end": segments[index]["end"],
            }
        )

    for index, edits in replacements.items():
        words = segments[index]["text"].split()
        for start, end, term in sorted(edits, reverse=True):
            words[start:end] = [term]
        segments[index]["text"] = " ".join(words)
    return {"status": "ok", "model": model, "terms": terms}
