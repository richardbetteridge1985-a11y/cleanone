import logging
import re


logger = logging.getLogger(__name__)

_RATING_PATTERN = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?Overall Rating:?\s*(?:\*\*)?\s*"
    r"\[?(Good|Fair|Bad|Not Applicable)\]?(?:\*\*)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_CODE_SECTION_PATTERN = re.compile(
    r"^\s*(?:#{1,6}\s+)?(?:\*\*)?Recommended Code / Structural Changes(?:\*\*)?",
    re.IGNORECASE,
)
_TEMPLATE_LINE_PATTERN = re.compile(
    r"Include this section ONLY if Rating is Fair or Bad|"
    r"Delete this entire section if Rating is Good or Not Applicable|"
    r"\[Existing file path|\[Create new file|generic-filename|"
    r"Show a concrete change for the location identified above",
    re.IGNORECASE,
)
_OVERALL_REVIEW_HEADINGS = (
    "**Implementation Decision:**",
    "**Changes Required for Pass**",
    "**Solution Summary**",
    "**Solution Document Rating:**",
    "**Documentation Summary**",
    "**Testing Plan Coverage:**",
    "**Testing Summary**",
)


def clean_conditional_code_section(response: str) -> str:
    lines = response.splitlines(keepends=True)
    rating_match = _RATING_PATTERN.search(response)
    rating = rating_match.group(1).casefold() if rating_match else None
    heading_index = next(
        (
            index
            for index, line in enumerate(lines)
            if _CODE_SECTION_PATTERN.match(line)
        ),
        None,
    )
    if heading_index is None:
        return response

    section_end = len(lines)
    in_code_block = False
    for index in range(heading_index + 1, len(lines)):
        stripped_line = lines[index].lstrip()
        if stripped_line.startswith("```"):
            in_code_block = not in_code_block
        elif not in_code_block and (
            re.match(r"^\s{0,3}#{1,6}\s+\S", lines[index])
            or re.match(r"^\s*\*\*[^*\n]+\*\*\s*$", lines[index])
        ):
            section_end = index
            break

    if rating in {"good", "not applicable"}:
        cleaned_lines = lines[:heading_index] + lines[section_end:]
        logger.info("Removed optional code section for rating=%s", rating)
        return re.sub(r"\n{3,}", "\n\n", "".join(cleaned_lines)).strip()

    heading = lines[heading_index]
    prefix_match = re.match(r"^\s*(?:#{1,6}\s+)?", heading)
    prefix = prefix_match.group(0) if prefix_match else ""
    canonical_heading = f"{prefix}**Recommended Code / Structural Changes**"
    if heading.endswith("\n"):
        canonical_heading += "\n"

    body = [
        line
        for line in lines[heading_index + 1:section_end]
        if not _TEMPLATE_LINE_PATTERN.search(line)
    ]
    substantive_body = [
        line.strip()
        for line in body
        if line.strip() not in {"", "```", "```python"}
    ]
    if not substantive_body:
        cleaned_lines = lines[:heading_index] + lines[section_end:]
        logger.info("Removed empty optional code section rating=%s", rating or "unknown")
        return re.sub(r"\n{3,}", "\n\n", "".join(cleaned_lines)).strip()

    cleaned_lines = (
        lines[:heading_index]
        + [canonical_heading]
        + body
        + lines[section_end:]
    )
    return re.sub(r"\n{3,}", "\n\n", "".join(cleaned_lines)).strip()


def format_overall_review(response: str) -> str:
    formatted = response.strip()
    for heading in _OVERALL_REVIEW_HEADINGS:
        formatted = re.sub(
            rf"[ \t]*{re.escape(heading)}[ \t]*",
            f"\n\n{heading}\n",
            formatted,
        )

    decision_heading = _OVERALL_REVIEW_HEADINGS[0]
    decision_start = formatted.find(decision_heading)
    if decision_start < 0:
        raise ValueError("Final review omitted the Implementation Decision section.")
    next_heading_positions = [
        position
        for heading in _OVERALL_REVIEW_HEADINGS[1:]
        if (position := formatted.find(heading, decision_start + len(decision_heading))) >= 0
    ]
    decision_end = min(next_heading_positions, default=len(formatted))
    decision_content = formatted[
        decision_start + len(decision_heading):decision_end
    ]
    decision_match = re.match(
        r"\s*(?:\*\*)?(Pass|Fail)\b(?:\*\*)?",
        decision_content,
        re.IGNORECASE,
    )
    if decision_match is None:
        raise ValueError("Final review did not return a Pass or Fail decision.")
    decision = decision_match.group(1).capitalize()
    formatted = (
        formatted[:decision_start]
        + f"{decision_heading}\n{decision}\n\n"
        + formatted[decision_end:].lstrip()
    )

    changes_heading = _OVERALL_REVIEW_HEADINGS[1]
    changes_start = formatted.find(changes_heading)
    if decision == "Pass" and changes_start >= 0:
        following_heading_positions = [
            position
            for heading in _OVERALL_REVIEW_HEADINGS[2:]
            if (position := formatted.find(heading, changes_start + len(changes_heading))) >= 0
        ]
        changes_end = min(following_heading_positions, default=len(formatted))
        formatted = (
            formatted[:changes_start].rstrip()
            + "\n\n"
            + formatted[changes_end:].lstrip()
        )
        logger.info("Removed changes-required section for Pass decision")
    elif decision == "Fail":
        if changes_start < 0:
            raise ValueError("Final review omitted required changes for a Fail decision.")
        following_heading_positions = [
            position
            for heading in _OVERALL_REVIEW_HEADINGS[2:]
            if (position := formatted.find(heading, changes_start + len(changes_heading))) >= 0
        ]
        changes_end = min(following_heading_positions, default=len(formatted))
        if "**Blocking change:**" not in formatted[changes_start:changes_end]:
            raise ValueError("Final review listed no blocking changes for a Fail decision.")

    formatted = re.sub(
        r"[ \t]*—[ \t]*(\*\*(?:Source|Design location):\*\*)",
        r"\n  \1",
        formatted,
    )
    formatted = re.sub(
        r"(?m)(?<!\n)[ \t]+\*\s+(?=\*\*Blocking change:\*\*)",
        "\n* ",
        formatted,
    )
    formatted = re.sub(
        r"(?m)^(?![ \t]*[*-])[ \t]*(?=\*\*Blocking change:\*\*)",
        "* ",
        formatted,
    )
    return re.sub(r"\n{3,}", "\n\n", formatted).strip()
