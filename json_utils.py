"""
JSON extraction and repair utilities for LLM responses.
Single source of truth for JSON parsing logic used by both
BaseAgent and OpenAIClient.
"""
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_JSON_NUMBER_RE = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")


def _normalize_json_text(text: str) -> str:
    """Normalize characters that commonly break JSON parsing."""
    return (
        text.lstrip("\ufeff")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
        .replace("‘", "'")
    )


def _escape_control_chars_in_strings(text: str) -> str:
    """Escape raw control characters that appear inside JSON strings."""
    result = []
    in_string = False
    escaped = False

    for char in text:
        if in_string:
            if escaped:
                result.append(char)
                escaped = False
                continue
            if char == "\\":
                result.append(char)
                escaped = True
                continue
            if char == '"':
                result.append(char)
                in_string = False
                continue
            if char == "\n":
                result.append("\\n")
                continue
            if char == "\r":
                result.append("\\r")
                continue
            if char == "\t":
                result.append("\\t")
                continue
            result.append(char)
            continue

        result.append(char)
        if char == '"':
            in_string = True

    return "".join(result)


def _replace_structural_ellipsis(text: str) -> str:
    """Replace placeholder ellipsis with valid empty JSON structures."""
    fixed = re.sub(r'\{\s*\.\.\.\s*\}', '{}', text)
    fixed = re.sub(r'\[\s*\.\.\.\s*\]', '[]', fixed)
    fixed = re.sub(r':\s*\.\.\.(?=\s*[,}\]])', ': null', fixed)
    fixed = re.sub(r',\s*\.\.\.(?=\s*[,}\]])', '', fixed)
    fixed = re.sub(r'(?m)^\s*\.\.\.\s*,?\s*$', '', fixed)
    return fixed


def _previous_significant_index(text: str, start: int) -> Optional[int]:
    """Find the previous non-whitespace character index."""
    for index in range(min(start, len(text) - 1), -1, -1):
        if not text[index].isspace():
            return index
    return None


def _next_significant_index(text: str, start: int) -> Optional[int]:
    """Find the next non-whitespace character index."""
    for index in range(max(start, 0), len(text)):
        if not text[index].isspace():
            return index
    return None


def _can_end_json_value(char: Optional[str]) -> bool:
    """Check whether a character may terminate a JSON value."""
    return char is not None and (char in {'"', '}', ']'} or char.isdigit() or char in {"e", "l"})


def _starts_json_literal(text: str, index: int) -> Optional[str]:
    """Return a JSON literal starting at index, if present."""
    for literal in ("true", "false", "null"):
        if text.startswith(literal, index):
            return literal
    return None


def _insert_missing_commas(text: str) -> str:
    """Insert commas between adjacent JSON values when only whitespace separates them."""
    result = []
    in_string = False
    escaped = False
    last_significant: Optional[str] = None
    index = 0

    while index < len(text):
        char = text[index]

        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
                last_significant = '"'
            index += 1
            continue

        if char.isspace():
            result.append(char)
            index += 1
            continue

        if char == '"':
            if _can_end_json_value(last_significant):
                result.append(",")
            result.append(char)
            in_string = True
            index += 1
            continue

        if char in "{[":
            if _can_end_json_value(last_significant):
                result.append(",")
            result.append(char)
            last_significant = char
            index += 1
            continue

        literal = _starts_json_literal(text, index)
        if literal:
            if _can_end_json_value(last_significant):
                result.append(",")
            result.append(literal)
            last_significant = literal[-1]
            index += len(literal)
            continue

        number_match = _JSON_NUMBER_RE.match(text, index)
        if number_match:
            if _can_end_json_value(last_significant):
                result.append(",")
            number_text = number_match.group(0)
            result.append(number_text)
            last_significant = number_text[-1]
            index = number_match.end()
            continue

        result.append(char)
        last_significant = char
        index += 1

    return "".join(result)


def _close_open_json_structures(text: str) -> str:
    """Close unterminated strings, arrays, and objects."""
    closers = []
    in_string = False
    escaped = False

    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            closers.append("}")
        elif char == "[":
            closers.append("]")
        elif char in "}]" and closers and char == closers[-1]:
            closers.pop()

    fixed = text
    if in_string:
        fixed += '"'

    fixed = re.sub(r',(\s*[}\]])', r'\1', fixed)
    fixed = re.sub(r'[:,]\s*$', '', fixed.rstrip())
    return fixed + "".join(reversed(closers))


def _repair_from_decode_error(text: str, error: json.JSONDecodeError) -> Optional[str]:
    """Apply a small targeted repair based on JSONDecodeError details."""
    pos = max(0, min(error.pos, len(text)))
    message = error.msg

    if "Expecting ',' delimiter" in message:
        current_index = _next_significant_index(text, pos)
        previous_index = _previous_significant_index(text, pos - 1)
        current_char = text[current_index] if current_index is not None else None
        previous_char = text[previous_index] if previous_index is not None else None
        if current_index is not None and _can_end_json_value(previous_char):
            if current_char in {'"', '{', '['} or current_char == "-" or (current_char and current_char.isdigit()):
                return text[:current_index] + "," + text[current_index:]
            if current_char and _starts_json_literal(text, current_index):
                return text[:current_index] + "," + text[current_index:]

    if "Expecting property name enclosed in double quotes" in message:
        current_index = _next_significant_index(text, pos)
        previous_index = _previous_significant_index(text, (current_index or pos) - 1)
        if (
            current_index is not None
            and previous_index is not None
            and text[current_index] == ","
            and text[previous_index] in "{[,"
        ):
            return text[:current_index] + text[current_index + 1:]
        if (
            current_index is not None
            and previous_index is not None
            and text[current_index] in "}]"
            and text[previous_index] == ","
        ):
            return text[:previous_index] + text[previous_index + 1:]

    if "Invalid control character" in message and pos < len(text):
        replacement = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}.get(text[pos])
        if replacement is not None:
            return text[:pos] + replacement + text[pos + 1:]

    if "Invalid \\escape" in message and pos < len(text):
        return text[:pos] + "\\" + text[pos:]

    if "Unterminated string" in message:
        return _close_open_json_structures(text + '"')

    if "Expecting value" in message:
        trimmed = re.sub(r'[:,]\s*$', '', text[:pos].rstrip())
        if trimmed:
            return _close_open_json_structures(trimmed)

    if "Extra data" in message:
        trimmed = text[:pos].rstrip()
        try:
            json.loads(trimmed)
            return trimmed
        except json.JSONDecodeError:
            return None

    return None


def fix_common_json_errors(text: str) -> str:
    """Try to fix common JSON formatting errors from LLM output.
    
    Args:
        text: JSON text with potential errors
        
    Returns:
        Fixed JSON text
    """
    fixed = _normalize_json_text(text)

    # Remove trailing commas before } or ]
    fixed = re.sub(r',(\s*[}\]])', r'\1', fixed)

    # Fix missing commas between array elements (common LLM error)
    # Pattern: "value"\n"value" -> "value",\n"value"
    fixed = re.sub(r'"\s*\n\s*"', '",\n"', fixed)
    
    # Fix missing commas between object properties
    # Pattern: ]\n"key" -> ],\n"key"
    fixed = re.sub(r'(\])\s*\n\s*(")', r'\1,\n\2', fixed)
    
    # Fix missing commas after } before {
    fixed = re.sub(r'(\})\s*\n\s*(\{)', r'\1,\n\2', fixed)
    
    # Fix missing commas after } before "
    fixed = re.sub(r'(\})\s*\n\s*(")', r'\1,\n\2', fixed)

    # Fix stray commas immediately after opening object/array brackets
    fixed = re.sub(r'([{\[])\s*,', r'\1', fixed)

    # Fix duplicated commas between values
    fixed = re.sub(r',\s*,+', ',', fixed)

    fixed = _replace_structural_ellipsis(fixed)
    fixed = _escape_control_chars_in_strings(fixed)
    fixed = _insert_missing_commas(fixed)
    fixed = _replace_structural_ellipsis(fixed)
    fixed = re.sub(r'([{\[])\s*,', r'\1', fixed)
    fixed = re.sub(r',\s*,+', ',', fixed)
    fixed = re.sub(r',(\s*[}\]])', r'\1', fixed)
    return _close_open_json_structures(fixed)


def repair_json_text(text: str, log_prefix: str = "", max_attempts: int = 8) -> Optional[str]:
    """Repair a JSON-like string until it becomes parseable or give up."""
    candidate = fix_common_json_errors(text)

    for attempt in range(max_attempts):
        try:
            json.loads(candidate)
            if attempt > 0:
                logger.info(f"{log_prefix}JSON repaired after {attempt} targeted fixes")
            return candidate
        except json.JSONDecodeError as error:
            updated = _repair_from_decode_error(candidate, error)
            if updated is None or updated == candidate:
                return None
            candidate = _close_open_json_structures(fix_common_json_errors(updated))

    return None


def extract_json_from_response(text: str, log_prefix: str = "") -> Optional[str]:
    """Extract JSON from LLM response that might contain markdown or other text.
    
    Tries multiple strategies in order:
    1. Parse entire text as JSON
    2. Fix common errors and parse
    3. Extract from markdown code blocks
    4. Find JSON objects by brace matching
    5. Last resort: first { to last }
    
    Args:
        text: Raw response text
        log_prefix: Optional prefix for log messages
        
    Returns:
        Extracted JSON string or None if not found
    """
    # Pre-processing: Strip <think>...</think> blocks (Qwen, DeepSeek reasoning models)
    # These models wrap their chain-of-thought in <think> tags before the actual response
    think_pattern = re.compile(r'<think>[\s\S]*?</think>', re.IGNORECASE)
    cleaned = think_pattern.sub('', text).strip()
    if cleaned != text:
        logger.info(f"{log_prefix}Stripped <think> block from response ({len(text)} -> {len(cleaned)} chars)")
        text = cleaned
    
    # Also handle unclosed <think> tags (model didn't close the tag)
    if re.match(r'^\s*<think>', text, re.IGNORECASE):
        # Find the first { after <think> that could be the start of JSON
        # but only if there's no </think> (already handled above)
        think_open = text.lower().find('<think>')
        first_brace = text.find('{', think_open)
        if first_brace != -1:
            text = text[first_brace:]
            logger.info(f"{log_prefix}Stripped unclosed <think> prefix")
    
    # Strategy 1: Try to parse the whole text as JSON
    try:
        json.loads(text)
        logger.info(f"{log_prefix}Entire response is valid JSON")
        return text
    except json.JSONDecodeError:
        pass

    # Strategy 2: Try to fix and parse
    fixed = repair_json_text(text, log_prefix=log_prefix)
    if fixed is not None:
        logger.info(f"{log_prefix}JSON fixed with basic corrections")
        return fixed

    # Strategy 3: Find JSON in markdown code blocks
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if json_match:
        json_text = json_match.group(1).strip()
        try:
            json.loads(json_text)
            logger.info(f"{log_prefix}Found valid JSON in markdown code block")
            return json_text
        except json.JSONDecodeError:
            # Try to fix
            fixed = repair_json_text(json_text, log_prefix=log_prefix)
            if fixed is not None:
                logger.info(f"{log_prefix}Fixed JSON from markdown code block")
                return fixed

    # Strategy 4: Find all JSON objects by brace matching and try each
    brace_count = 0
    json_start = -1
    candidates = []
    
    for i, char in enumerate(text):
        if char == '{':
            if brace_count == 0:
                json_start = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and json_start != -1:
                candidates.append(text[json_start:i + 1])
                json_start = -1
    
    # Try each candidate, starting from the largest
    candidates.sort(key=len, reverse=True)
    
    for candidate in candidates:
        try:
            json.loads(candidate)
            logger.info(f"{log_prefix}Found valid JSON object ({len(candidate)} chars)")
            return candidate
        except json.JSONDecodeError:
            # Try to fix
            fixed = repair_json_text(candidate, log_prefix=log_prefix)
            if fixed is not None:
                logger.info(f"{log_prefix}Fixed JSON candidate")
                return fixed

    # Strategy 5: Last resort — find first { and last } and try to fix
    first_brace = text.find('{')
    last_brace = text.rfind('}')

    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_text = text[first_brace:last_brace + 1]
        try:
            json.loads(json_text)
            logger.info(f"{log_prefix}Extracted text between first and last brace")
            return json_text
        except json.JSONDecodeError:
            # Try to fix
            fixed = repair_json_text(json_text, log_prefix=log_prefix)
            if fixed is not None:
                logger.info(f"{log_prefix}Fixed JSON (last resort)")
                return fixed
            logger.warning(f"{log_prefix}Returning potentially broken JSON (last resort)")
            return json_text

    if first_brace != -1:
        json_text = text[first_brace:]
        fixed = repair_json_text(json_text, log_prefix=log_prefix)
        if fixed is not None:
            logger.info(f"{log_prefix}Recovered truncated JSON by closing open structures")
            return fixed

    logger.error(f"{log_prefix}Could not extract JSON from response")
    return None
