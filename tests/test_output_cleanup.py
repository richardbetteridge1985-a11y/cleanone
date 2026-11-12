from src.output_cleanup import clean_conditional_code_section


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
