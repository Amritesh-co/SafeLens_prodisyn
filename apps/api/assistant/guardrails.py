"""
Input and output guardrails for the assistant.

Input:  length limits, history validation, prompt-injection / data-exfiltration
        pattern blocking.
Output: PII redaction, grounding check (factual claims require a tool call),
        leak check for system-prompt / tool internals.
"""

import re

MAX_QUESTION_CHARS = 1000
MAX_HISTORY_TURNS = 10
MAX_HISTORY_MESSAGE_CHARS = 2000

REFUSAL_OFF_TOPIC = (
    "I can only answer questions about SafeLens safety data you have access to "
    "(incidents, cameras, locations and their review status)."
)
REFUSAL_BLOCKED = "I can't help with that request."
REFUSAL_NOT_FOUND = (
    "I couldn't find that data, or it isn't available to your account."
)
REFUSAL_UNGROUNDED = (
    "I couldn't verify an answer against the SafeLens data. "
    "Please rephrase your question, for example with a date range or location."
)

# Attempts to override instructions, extract internals, or reach raw data/other tenants.
_BLOCK_PATTERNS = [
    r'ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions|rules|prompts?)',
    r'disregard\s+(all\s+|any\s+|the\s+)?(previous|prior|above|your)\s+(instructions|rules)',
    r'(reveal|show|print|repeat|output)\s+(me\s+)?(your|the)\s+(system\s+prompt|instructions|rules|prompt)',
    r'\bsystem\s+prompt\b',
    r'\bjailbreak\b',
    r'\bdeveloper\s+mode\b',
    r'\bact\s+as\s+(an?\s+)?(unrestricted|dan)\b',
    r'\b(drop|truncate|alter)\s+table\b',
    r'\b(delete\s+from|insert\s+into|update\s+\w+\s+set)\b',
    r'\bselect\s+.+\s+from\s+\w+',
    r'\b(password|passwd|api[\s_-]?key|secret[\s_-]?key|access[\s_-]?token|auth\s+token)s?\b',
    r'\bother\s+(tenants?|compan(y|ies)|customers?)\b',
    r'\ball\s+tenants\b',
]
_BLOCK_RE = [re.compile(p, re.IGNORECASE) for p in _BLOCK_PATTERNS]

_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_PHONE_RE = re.compile(r'(?<!\d)(?:\+?\d[\d\s-]{8,}\d)(?!\d)')
_LEAK_MARKERS = ('SAFELENS_ASSISTANT_RULES', 'review_comment_untrusted', '"type": "function"')


class GuardrailViolation(Exception):
    def __init__(self, message, reason):
        super().__init__(message)
        self.user_message = message
        self.reason = reason


def check_question(question):
    if not isinstance(question, str) or not question.strip():
        raise GuardrailViolation("Please enter a question.", 'empty')
    if len(question) > MAX_QUESTION_CHARS:
        raise GuardrailViolation(
            f"Questions are limited to {MAX_QUESTION_CHARS} characters.", 'too_long'
        )
    for pattern in _BLOCK_RE:
        if pattern.search(question):
            raise GuardrailViolation(REFUSAL_BLOCKED, f'blocked_pattern:{pattern.pattern[:40]}')
    return question.strip()


def clean_history(history):
    """
    Accept prior turns from the client as plain text only. Client-supplied
    'system' or 'tool' roles are dropped so they can't inject instructions or
    fake tool results.
    """
    if not history:
        return []
    if not isinstance(history, list):
        raise GuardrailViolation("history must be a list of {role, content} objects.", 'bad_history')

    cleaned = []
    for item in history[-MAX_HISTORY_TURNS * 2:]:
        if not isinstance(item, dict):
            continue
        role = item.get('role')
        content = item.get('content')
        if role not in ('user', 'assistant') or not isinstance(content, str):
            continue
        content = content[:MAX_HISTORY_MESSAGE_CHARS]
        if role == 'user':
            for pattern in _BLOCK_RE:
                if pattern.search(content):
                    raise GuardrailViolation(REFUSAL_BLOCKED, 'blocked_pattern_in_history')
        cleaned.append({'role': role, 'content': content})
    return cleaned


_DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')


def _redact_phone(match):
    candidate = match.group(0)
    # Leave dates/timestamps alone; only redact phone-length digit runs.
    if _DATE_RE.search(candidate):
        return candidate
    digits = sum(ch.isdigit() for ch in candidate)
    return '[redacted number]' if 10 <= digits <= 15 else candidate


def redact(text):
    text = _EMAIL_RE.sub('[redacted email]', text)
    text = _PHONE_RE.sub(_redact_phone, text)
    return text


def check_answer(answer, tool_calls_made, tool_calls_rejected=0):
    """
    Returns (final_answer, status). status is 'ok', 'not_found', 'ungrounded' or 'leak'.
    """
    answer = (answer or '').strip()

    # Every lookup was rejected (missing / out of scope): use a fixed message so
    # the model can't embellish, and so we never confirm whether a record exists.
    if tool_calls_made == 0 and tool_calls_rejected > 0:
        return REFUSAL_NOT_FOUND, 'not_found'
    if not answer:
        return REFUSAL_UNGROUNDED, 'ungrounded'

    if any(marker in answer for marker in _LEAK_MARKERS):
        return REFUSAL_BLOCKED, 'leak'

    # Grounding: an answer that states numbers/facts without having queried the
    # database is not allowed. Plain refusals/clarifying questions are fine.
    if tool_calls_made == 0 and answer != REFUSAL_OFF_TOPIC and re.search(r'\d', answer):
        return REFUSAL_UNGROUNDED, 'ungrounded'

    return redact(answer), 'ok'
