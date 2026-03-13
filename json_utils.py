"""
JSON extraction and repair utilities for LLM responses.
Single source of truth for JSON parsing logic used by both
BaseAgent and OpenAIClient.
"""
import json
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def fix_common_json_errors(text: str) -> str:
    """Try to fix common JSON formatting errors from LLM output.
    
    Args:
        text: JSON text with potential errors
        
    Returns:
        Fixed JSON text
    """
    # Remove trailing commas before } or ]
    fixed = re.sub(r',(\s*[}\]])', r'\1', text)
    
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
    
    return fixed


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
    try:
        fixed = fix_common_json_errors(text)
        json.loads(fixed)
        logger.info(f"{log_prefix}JSON fixed with basic corrections")
        return fixed
    except json.JSONDecodeError:
        pass
    
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
            try:
                fixed = fix_common_json_errors(json_text)
                json.loads(fixed)
                logger.info(f"{log_prefix}Fixed JSON from markdown code block")
                return fixed
            except json.JSONDecodeError:
                pass
    
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
            try:
                fixed = fix_common_json_errors(candidate)
                json.loads(fixed)
                logger.info(f"{log_prefix}Fixed JSON candidate")
                return fixed
            except json.JSONDecodeError:
                continue
    
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
            try:
                fixed = fix_common_json_errors(json_text)
                json.loads(fixed)
                logger.info(f"{log_prefix}Fixed JSON (last resort)")
                return fixed
            except json.JSONDecodeError:
                # Return original even if broken — let caller handle error
                logger.warning(f"{log_prefix}Returning potentially broken JSON (last resort)")
                return json_text
    
    logger.error(f"{log_prefix}Could not extract JSON from response")
    return None
