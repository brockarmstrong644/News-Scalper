"""Hybrid LLM layer.

The numeric signals in the CSV are pure rule-based math and never touch the
model. The model only writes the human-readable "notes" column, interpreting
the already-computed numbers. If the anthropic SDK or API key is missing the
agent still works - notes fall back to a rule-based sentence.
"""

import json

try:
    import anthropic
except ImportError:
    anthropic = None

SYSTEM_PROMPT = (
    "You are a market analyst writing the 'notes' field of one CSV row that an "
    "algorithmic trading program's operators will read. You are given the "
    "already-computed earnings, market, Fed, and economic data for one stock as "
    "JSON. Write 2-3 plain sentences interpreting it: was the earnings report "
    "good or bad and why, and does the macro backdrop help or hurt. Do not "
    "invent numbers not in the data. Output plain text only - no markdown, no "
    "line breaks."
)


def _fallback_notes(report):
    words = {1: "positive", 0: "neutral", -1: "negative"}
    return (
        f"Earnings {words[report['earnings_signal']]} "
        f"(surprise {report['surprise_pct']}%); "
        f"market {words[report['market_signal']]}, "
        f"fed {words[report['fed_signal']]}, "
        f"economy {words[report['econ_signal']]}."
    )


def write_notes(report, raw_context, settings):
    """Return the notes string for one CSV row.

    report      -- the final numeric row (signals, surprise_pct, ...)
    raw_context -- dict of the underlying skill outputs for extra color
    settings    -- config/settings.json contents (api key + model)
    """
    if not settings.get("llm_notes_enabled", True):
        return _fallback_notes(report)
    if anthropic is None:
        return _fallback_notes(report) + " (anthropic SDK not installed)"

    api_key = settings.get("anthropic_api_key") or None
    model = settings.get("model") or "claude-opus-4-8"

    try:
        # No api_key arg -> SDK resolves ANTHROPIC_API_KEY / ant login profile
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        payload = {"row": report, "context": raw_context}
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(payload)}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        text = " ".join(text.split())  # collapse any stray newlines
        return text or _fallback_notes(report)
    except Exception as exc:  # keep the pipeline alive on any API failure
        return _fallback_notes(report) + f" (llm unavailable: {exc})"
