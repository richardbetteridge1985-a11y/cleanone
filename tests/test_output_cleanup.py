import pytest

from src.output_cleanup import clean_conditional_code_section, format_overall_review


def test_good_rating_removes_optional_code_section_and_template_text():
    response = (
        "#### Overall Rating: Good\n\n"
        "**General Assessment**\nNo structural rework is needed.\n\n"
        "**Recommended Code / Structural Changes** "
        "*(Include this section ONLY if Rating is Fair or Bad. "
        "Delete this entire section if Rating is Good or Not Applicable.)*\n"
        "**Location:** [Existing file path — change the named function]\n\n"
        "```python\n# Show a concrete change for the location identified above\n```"
    )

    cleaned = clean_conditional_code_section(response)

    assert "#### Overall Rating: Good" in cleaned
    assert "General Assessment" in cleaned
    assert "Recommended Code / Structural Changes" not in cleaned
    assert "Include this section ONLY" not in cleaned


def test_fair_rating_keeps_real_recommendation_but_removes_template_instruction():
    response = (
        "#### Overall Rating: Fair\n\n"
        "**Recommended Code / Structural Changes** "
        "*(Include this section ONLY if Rating is Fair or Bad.)*\n"
        "**Location:** src/domain.py — update the aggregate boundary.\n\n"
        "```python\nclass OrderAggregate: ...\n```"
    )

    cleaned = clean_conditional_code_section(response)

    assert "**Recommended Code / Structural Changes**" in cleaned
    assert "**Location:** src/domain.py" in cleaned
    assert "class OrderAggregate" in cleaned
    assert "Include this section ONLY" not in cleaned


def test_empty_optional_code_section_is_removed_even_without_rating():
    response = (
        "**Recommended Code / Structural Changes**\n"
        "*(Include this section ONLY if Rating is Fair or Bad.)*\n"
        "**Location:** [Existing file path — name the section]\n"
        "```python\n# Show a concrete change for the location identified above\n```"
    )

    cleaned = clean_conditional_code_section(response)

    assert "Recommended Code / Structural Changes" not in cleaned


def test_template_rating_list_is_not_treated_as_an_actual_good_rating():
    response = (
        "#### Overall Rating: [Good | Fair | Bad | Not Applicable]\n\n"
        "**Recommended Code / Structural Changes**\n"
        "**Location:** src/domain.py — update the aggregate boundary.\n"
    )

    cleaned = clean_conditional_code_section(response)

    assert "**Recommended Code / Structural Changes**" in cleaned
    assert "**Location:** src/domain.py" in cleaned


def test_overall_review_formatter_separates_flattened_sections_and_blocker_details():
    response = (
        "**Implementation Decision:** Fail "
        "**Changes Required for Pass** * **Blocking change:** Implement "
        "additional authentication mechanisms — **Source:** Testing & "
        "Verification Strategist — **Design location:** Architectural Diagram 2 "
        "**Solution Summary** The proposal presents a C4 model-based architecture. "
        "**Solution Document Rating:** Good "
        "**Documentation Summary** The document provides a comprehensive overview. "
        "**Testing Plan Coverage:** Good "
        "**Testing Summary** The documented plan covers most requirements."
    )

    formatted = format_overall_review(response)

    assert "**Implementation Decision:**\nFail" in formatted
    assert "\n\n**Changes Required for Pass**\n* **Blocking change:**" in formatted
    assert (
        "additional authentication mechanisms\n  **Source:** "
        "Testing & Verification Strategist\n  **Design location:** "
        "Architectural Diagram 2"
    ) in formatted
    assert "\n\n**Solution Summary**\nThe proposal" in formatted
    assert "\n\n**Solution Document Rating:**\nGood" in formatted
    assert "\n\n**Documentation Summary**\nThe document" in formatted
    assert "\n\n**Testing Plan Coverage:**\nGood" in formatted
    assert "\n\n**Testing Summary**\nThe documented" in formatted


def test_pass_decision_removes_reason_and_changes_required_section():
    response = (
        "**Implementation Decision:** Pass The design should meet its requirements. "
        "**Changes Required for Pass** * **Blocking change:** Make an unnecessary "
        "change — **Source:** Cloud Specialist — **Design location:** Diagram 1 "
        "**Solution Summary** The solution meets the stated needs."
    )

    formatted = format_overall_review(response)

    assert formatted.startswith("**Implementation Decision:**\nPass")
    assert "The design should meet its requirements." not in formatted
    assert "**Changes Required for Pass**" not in formatted
    assert "Make an unnecessary change" not in formatted
    assert "\n\n**Solution Summary**\nThe solution" in formatted


def test_fail_decision_requires_changes_section():
    with pytest.raises(ValueError, match="omitted required changes"):
        format_overall_review(
            "**Implementation Decision:** Fail\n\n"
            "**Solution Summary**\nThe design has a blocking issue."
        )


def test_fail_decision_requires_at_least_one_blocking_change():
    with pytest.raises(ValueError, match="listed no blocking changes"):
        format_overall_review(
            "**Implementation Decision:** Fail\n\n"
            "**Changes Required for Pass**\nNo changes listed.\n\n"
            "**Solution Summary**\nThe design has a blocking issue."
        )
