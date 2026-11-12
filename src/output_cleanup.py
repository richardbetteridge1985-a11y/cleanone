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
