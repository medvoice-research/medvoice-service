"""Decision rules of the medical-term guard, with Whisper and SemIf replaced by fakes."""

import pytest

from app.services import term_guard

TEXT = "đang dùng men hormone huyết áp hôm nay"


class FakeScorer:
    """Word probabilities flag 'men hormone'; log-probabilities come from a table."""

    logprobs_by_term: dict = {}

    def __init__(self, whisper, audio, start, end, language):
        pass

    def word_probs(self, text):
        return [0.9 if w not in ("men", "hormone") else 0.2 for w in text.split()]

    def logprobs(self, texts):
        return [0.0 if t == TEXT else self.logprobs_by_term.get(t.split()[2], -99.0) for t in texts]


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr(term_guard, "_SegmentScorer", FakeScorer)
    monkeypatch.setattr(term_guard, "_lexicon", lambda: {"metformin": "metformin", "methadone": "methadone"})

    def go(logprobs, p_misheard=0.95):
        FakeScorer.logprobs_by_term = logprobs
        monkeypatch.setattr(term_guard, "_semif", lambda state, phrases: ("fake", [p_misheard] * len(phrases)))
        segments = [{"text": " " + TEXT, "start": 0.0, "end": 5.0}]
        return segments, term_guard.guard_terms(segments, None, None, "vi")

    return go


def test_corrects_when_one_term_sounds_right_and_clearly_wins(run):
    segments, review = run({"metformin": -3.0, "methadone": -20.0})
    assert segments[0]["text"] == "đang dùng metformin huyết áp hôm nay"
    assert review["terms"][0]["action"] == "corrected"
    assert review["terms"][0]["replacement"] == "metformin"


def test_flags_without_editing_when_two_terms_sound_alike(run):
    segments, review = run({"metformin": -3.0, "methadone": -4.0})
    assert segments[0]["text"] == " " + TEXT
    assert review["terms"][0]["action"] == "flagged"
    assert [s["term"] for s in review["terms"][0]["suggestions"]] == ["metformin", "methadone"]


def test_flags_when_best_term_sounds_unlike_the_audio(run):
    segments, review = run({"metformin": -30.0, "methadone": -60.0})
    assert segments[0]["text"] == " " + TEXT
    assert review["terms"][0]["action"] == "flagged"


def test_ignores_suspect_words_semif_calls_ordinary(run):
    segments, review = run({"metformin": -3.0}, p_misheard=0.1)
    assert segments[0]["text"] == " " + TEXT
    assert review == {"status": "ok", "model": "fake", "terms": []}


def test_semif_down_leaves_text_and_reports_unavailable(run, monkeypatch):
    def down(state, phrases):
        raise ConnectionError("refused")

    FakeScorer.logprobs_by_term = {"metformin": -3.0}
    monkeypatch.setattr(term_guard, "_semif", down)
    segments = [{"text": " " + TEXT, "start": 0.0, "end": 5.0}]
    assert term_guard.guard_terms(segments, None, None, "vi") == {"status": "unavailable", "terms": []}
    assert segments[0]["text"] == " " + TEXT


def test_low_runs_skip_the_first_word_and_merge_neighbours():
    assert term_guard._low_runs([0.0, 0.9, 0.2, 0.3, 0.9, 0.1], 0.5) == [(2, 4), (5, 6)]
