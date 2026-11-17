"""
LLM invocation helpers for OpenRedu.

Provides:
  - _call_bedrock_anthropic(): Claude models via AWS Bedrock
  - _call_bedrock_mistral():   Mistral via AWS Bedrock
  - llm_with_escalation():     3-tier fallback (primary → middle → escalate)

Model IDs (from phase3_enrich.py — exact Bedrock strings):
  extraction_primary   = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
  extraction_middle    = "mistral.mistral-large-3-675b-instruct"
  extraction_escalate  = "us.anthropic.claude-sonnet-4-6"
  standardization_llm  = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
"""
import json
import re
import time
import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

import boto3
from dotenv import load_dotenv

# Bedrock bearer-token authentication is configured in the repository root.
# Use an explicit path so this works regardless of the process working directory.
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

log = logging.getLogger(__name__)

# Lazy client — initialized on first call
_BEDROCK_CLIENT = None


def _get_bedrock_client():
    global _BEDROCK_CLIENT
    if _BEDROCK_CLIENT is None:
        region = os.getenv("AWS_REGION", "us-east-1")
        _BEDROCK_CLIENT = boto3.client("bedrock-runtime", region_name=region)
    return _BEDROCK_CLIENT


# ── JSON parsing helpers ──────────────────────────────────────────────────────

def _parse_json_response(raw: str) -> dict:
    """
    Strip markdown fences and parse JSON.
    Handles:
    - Single dict
    - List of dicts → first element
    - Extra text after JSON ("Extra data") → extract first {...} block
    """
    cleaned = re.sub(
        r"^```json\s*|^```\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE
    ).strip()

    # 1. Try normal parsing
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
            return parsed[0]
        raise ValueError(f"Unexpected JSON shape: {type(parsed)}")
    except json.JSONDecodeError:
        pass

    # 2. "Extra data" case: extract only the first {...} block
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)?\}', cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # 3. Extract nested JSON from a wider span
    depth, start = 0, -1
    for i, ch in enumerate(cleaned):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    return json.loads(cleaned[start:i+1])
                except json.JSONDecodeError:
                    pass
                break

    raise ValueError(f"Cannot parse JSON from: {cleaned[:100]}")


# ── Low-level callers ─────────────────────────────────────────────────────────

def _anthropic_body(user_msg: str, system_prompt: str, max_tokens: int, temperature: Optional[float]) -> str:
    # temperature=None leaves it out of the request (provider default) — the original behaviour.
    body = {"anthropic_version": "bedrock-2023-05-31", "max_tokens": max_tokens}
    if temperature is not None:
        body["temperature"] = temperature
    body["system"] = system_prompt
    body["messages"] = [{"role": "user", "content": user_msg}]
    return json.dumps(body)


def _call_bedrock_anthropic(
    model: str,
    user_msg: str,
    system_prompt: str,
    max_tokens: int = 400,
    temperature: Optional[float] = None,
) -> dict:
    """Call any Claude model via Bedrock Anthropic format."""
    body = _anthropic_body(user_msg, system_prompt, max_tokens, temperature)
    resp = _get_bedrock_client().invoke_model(modelId=model, body=body)
    raw = json.loads(resp["body"].read())["content"][0]["text"].strip()
    return _parse_json_response(raw)


def call_bedrock_anthropic_raw(
    model: str,
    user_msg: str,
    system_prompt: str,
    max_tokens: int = 400,
    temperature: Optional[float] = None,
) -> Tuple[str, int, int]:
    """Like _call_bedrock_anthropic but returns (raw_text, input_tokens, output_tokens) without parsing."""
    body = _anthropic_body(user_msg, system_prompt, max_tokens, temperature)
    resp = _get_bedrock_client().invoke_model(modelId=model, body=body)
    js = json.loads(resp["body"].read())
    usage = js.get("usage", {})
    return js["content"][0]["text"].strip(), usage.get("input_tokens", 0), usage.get("output_tokens", 0)


def _call_bedrock_mistral(
    user_msg: str,
    system_prompt: str,
    max_tokens: int = 400,
    model: str = "mistral.mistral-large-3-675b-instruct",
) -> dict:
    """Call Mistral via Bedrock (different request format)."""
    body = json.dumps({
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_msg},
        ],
        "max_tokens": max_tokens,
    })
    resp = _get_bedrock_client().invoke_model(modelId=model, body=body)
    raw = json.loads(resp["body"].read())["choices"][0]["message"]["content"].strip()
    return _parse_json_response(raw)


# ── validate_fn implementations ───────────────────────────────────────────────

VALID_LATERALITY = {
    "right", "left", "bilateral", "central", "midline", "mediastinal", "n/a",
}


def valid_extraction_schema(result: dict) -> bool:
    """
    Valid if finding, diagnosis, laterality are all non-empty strings
    and laterality is one of the allowed values.
    Invalid laterality triggers a retry so the LLM corrects it.
    """
    if not isinstance(result, dict):
        return False
    finding   = result.get("finding", "")
    diagnosis = result.get("diagnosis", "")
    laterality = (result.get("laterality") or "").strip().lower()
    if (finding or "").strip().lower() in ("", "extraction failed", "n/a", "unclear", "not available"):
        return False
    if (diagnosis or "").strip().lower() in ("", "extraction failed", "n/a", "unclear", "not available", "unknown", "uncertain"):
        return False
    if laterality not in VALID_LATERALITY:
        return False
    return True


def valid_clinical_check_schema(result: dict) -> bool:
    """Valid if is_clinical is a bool."""
    return isinstance(result, dict) and isinstance(result.get("is_clinical"), bool)


def valid_concept_extraction_schema(result: dict) -> bool:
    """Valid if concepts is a list and mappable is a bool."""
    return (
        isinstance(result, dict)
        and isinstance(result.get("concepts"), list)
        and isinstance(result.get("mappable"), bool)
    )


def valid_self_check_schema(result: dict) -> bool:
    """Valid if consistent is a bool."""
    return isinstance(result, dict) and isinstance(result.get("consistent"), bool)


# ── Main escalation helper ────────────────────────────────────────────────────

def llm_with_escalation(
    prompt: str,
    system_prompt: str,
    primary: str,
    escalate: str,
    validate_fn: Callable[[dict], bool],
    *,
    middle: Optional[str] = None,
    max_retries: int = 3,
    sleep_s: float = 3.0,
    max_tokens: int = 400,
) -> Tuple[Optional[dict], str, int]:
    """
    Call LLM with 3-tier fallback: primary → middle (optional) → escalate.

    1. Try primary model up to max_retries times with exponential backoff.
    2. If still failing, try middle tier once (if provided).
    3. If still failing, try escalate model once.
    4. If all fail, return (None, "all_failed", total_attempts).

    Returns: (result_dict, model_id_used, total_attempts)
    result_dict is None on total failure.

    Caller is responsible for updating state.models_used with model_id_used.
    """
    total_attempts = 0
    is_mistral = middle and "mistral" in middle.lower()

    def _call(model_id: str) -> dict:
        if "mistral" in model_id.lower():
            return _call_bedrock_mistral(
                user_msg=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                model=model_id,
            )
        return _call_bedrock_anthropic(
            model=model_id,
            user_msg=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )

    # ── Tier 1: primary (Haiku) ───────────────────────────────────────────────
    for attempt in range(1, max_retries + 1):
        total_attempts += 1
        try:
            result = _call(primary)
            if validate_fn(result):
                return result, primary, total_attempts
            log.warning(f"{primary} attempt {attempt}/{max_retries}: schema invalid")
        except Exception as e:
            log.warning(f"{primary} attempt {attempt}/{max_retries} error: {e}")
            if "ThrottlingException" in str(e):
                time.sleep(min(sleep_s * (2 ** attempt), 60))
                continue
        if attempt < max_retries:
            time.sleep(sleep_s * attempt)

    # ── Tier 2: middle (Mistral) ──────────────────────────────────────────────
    if middle:
        total_attempts += 1
        try:
            result = _call(middle)
            if validate_fn(result):
                return result, middle, total_attempts
            log.warning(f"{middle} fallback: schema invalid")
        except Exception as e:
            log.warning(f"{middle} fallback error: {e}")

    # ── Tier 3: escalate (Sonnet) ─────────────────────────────────────────────
    total_attempts += 1
    try:
        result = _call(escalate)
        if validate_fn(result):
            return result, escalate, total_attempts
        log.warning(f"{escalate} escalation: schema invalid")
    except Exception as e:
        log.warning(f"{escalate} escalation error: {e}")

    return None, "all_failed", total_attempts
