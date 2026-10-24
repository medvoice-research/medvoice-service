"""Pure tests for MedicalLLMService._parse_soap_response (offline, no LM Studio)."""

import pytest

from app.llm.medical_llm_service import MedicalLLMService

SECTIONS = ("subjective", "objective", "assessment", "plan")
CONTENT = {
    "subjective": "A 52-year-old female presents with chest pain on exertion.",
    "objective": "BP 150/90 mmHg, HR 90/min.",
    "assessment": "Atypical chest pain; rule out ischemia.",
    "plan": "ECG, echocardiogram, aspirin; follow-up in one week.",
}


@pytest.fixture
def parse():
    return MedicalLLMService(client=object())._parse_soap_response


def _inline(header_fmt):
    return "\n\n".join(f"{header_fmt.format(name.capitalize())} {CONTENT[name]}" for name in SECTIONS)


def _standalone(header_fmt):
    return "\n\n".join(f"{header_fmt.format(name.capitalize())}\n{CONTENT[name]}" for name in SECTIONS)


def test_plain_colon_inline_header(parse):
    assert parse(_inline("{}:")) == CONTENT


def test_bold_then_colon_inline_header(parse):
    assert parse(_inline("**{}**:")) == CONTENT


def test_bold_colon_inside_inline_header(parse):
    assert parse(_inline("**{}:**")) == CONTENT


def test_h2_standalone_header(parse):
    assert parse(_standalone("## {}")) == CONTENT


def test_h3_colon_standalone_header(parse):
    assert parse(_standalone("### {}:")) == CONTENT


def test_bold_standalone_header(parse):
    assert parse(_standalone("**{}**")) == CONTENT


def test_bold_colon_inside_standalone_header(parse):
    assert parse(_standalone("**{}:**")) == CONTENT


def test_headers_are_case_insensitive(parse):
    assert parse("**SUBJECTIVE:** chest pain\nplan: rest") == {
        "subjective": "chest pain",
        "objective": "",
        "assessment": "",
        "plan": "rest",
    }

def test_vietnamese_headers_map_to_soap_sections(parse):
    response = "**Chủ quan:** đau đầu\n**Khách quan:** huyết áp ổn\n**Đánh giá:** đau nửa đầu\n**Kế hoạch:** nghỉ ngơi"
    assert parse(response) == {
        "subjective": "đau đầu",
        "objective": "huyết áp ổn",
        "assessment": "đau nửa đầu",
        "plan": "nghỉ ngơi",
    }


def test_regression_bold_colon_inside_header_leaks_asterisks(parse):
    response = (
        "**Subjective:** A 52-year-old female patient presents with chest pain and shortness of breath "
        "on exertion for the past two weeks.\n\n"
        "**Objective:** Blood pressure is 150/90 mmHg, pulse is 90/min.\n\n"
        "**Assessment:** Atypical chest pain.\n\n"
        "**Plan:** N/A"
    )

    sections = parse(response)

    assert sections["subjective"].startswith("A 52-year-old female")
    assert sections["plan"] == "N/A"
    assert not any("**" in text for text in sections.values())


def test_content_inline_bold_is_unwrapped_and_bullets_kept(parse):
    response = "**Plan:** **Aspirin** 81 mg daily\n- ECG today\n* **Echo** within a week\n__Follow-up in 1 week__"

    assert parse(response)["plan"] == "Aspirin 81 mg daily\n- ECG today\n* Echo within a week\nFollow-up in 1 week"

def test_nested_and_unbalanced_emphasis_markers_are_removed(parse):
    response = "**Plan:**\nTake **dose **two** daily** and __aspirin__ with **an unclosed phrase"
    assert parse(response)["plan"] == "Take dose two daily and aspirin with an unclosed phrase"


def test_word_starting_a_content_line_is_not_a_header(parse):
    response = "**Plan:**\nPlan to repeat troponin in 6 hours."

    assert parse(response)["plan"] == "Plan to repeat troponin in 6 hours."
