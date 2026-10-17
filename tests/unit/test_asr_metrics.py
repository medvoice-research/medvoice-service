from app.services.asr_metrics import cer, entity_spans, normalize, term_hits, wer


def test_normalize_keeps_tones_drops_case_punct_and_extra_space():
    assert normalize("  Đau  ĐẦU, sốt!\n") == "đau đầu sốt"


def test_normalize_composes_decomposed_unicode():
    # "ế" typed as e + circumflex + acute must equal precomposed "ế".
    assert normalize("bê\u0301nh") == normalize("bếnh")


def test_normalize_spells_numbers_the_way_vietmed_references_do():
    assert normalize("dưới 1%") == "dưới một phần trăm"
    assert normalize("55 tuổi") == "năm mươi lăm tuổi"
    assert normalize("21 ngày, 10 viên, 15 ml") == "hai mươi mốt ngày mười viên mười lăm ml"
    assert normalize("105") == "một trăm linh năm"
    assert normalize("2024") == "hai nghìn không trăm hai mươi bốn"
    assert normalize("14") == "mười bốn"


def test_wer_counts_substitution_insertion_deletion():
    assert wer("a b c", "a x c") == (1, 3)
    assert wer("a b c", "a b c d") == (1, 3)
    assert wer("a b c", "a c") == (1, 3)
    assert wer("", "a") == (1, 0)


def test_cer_treats_tone_change_as_one_edit():
    assert cer("má", "mà") == (1, 2)


def test_entity_spans_joins_bio_runs_and_filters_labels():
    words = ["bây", "giờ", "rong", "kinh", "và", "đau", "bụng"]
    labels = [
        "B-DATETIME",
        "I-DATETIME",
        "B-DISEASESYMTOM",
        "I-DISEASESYMTOM",
        "0",
        "B-DISEASESYMTOM",
        "I-DISEASESYMTOM",
    ]
    assert entity_spans(words, labels, keep={"DISEASESYMTOM"}) == ["rong kinh", "đau bụng"]


def test_entity_spans_new_b_tag_closes_previous_span():
    words = ["sốt", "ho"]
    labels = ["B-DISEASESYMTOM", "B-DISEASESYMTOM"]
    assert entity_spans(words, labels, keep={"DISEASESYMTOM"}) == ["sốt", "ho"]


def test_term_hits_matches_whole_words_only():
    hyp = "bệnh nhân bị rong kinh, không sốt"
    assert term_hits(["rong kinh", "sốt"], hyp) == 2
    # "kinh" alone is present as a word; "ong" is only a substring of "rong".
    assert term_hits(["ong"], hyp) == 0
    assert term_hits(["Rong Kinh"], hyp) == 1
