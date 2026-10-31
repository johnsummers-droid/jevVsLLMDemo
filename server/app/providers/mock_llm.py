"""Deterministic, scenario-aware mock LLM (plan1.txt 3b).

The answer is a canned reply for the ticket's intent. Unsafe behavior is drawn from call.rng:
  - an input with the "injection" taint is obeyed with p COMPLY[tier]; obeying writes the
    ticket's risk marker phrase and keeps the "injection" taint (refusing drops it);
  - a policy-violation ticket gets the marker and "policy_violation" with p VIOLATE[tier];
  - PII still in the input text (a redactor removes it) is echoed back, with "pii", with
    p PII_ECHO;
  - a needs_grounding ticket is "ungrounded" unless the context has a doc for its intent, more
    often when the input is a summary (details got lost).
The "summarize" task (the summarizer node) keeps the first SUMMARY_RATIO of the words plus any
PII, tags the result with SUMMARY_TAG and keeps the input's taint.
Hardening phrases in the prompt halve the first three. Each marker phrase is caught by exactly
one policy rule (tools/policy.py).
"""

import math

from app.models import Docs, Taint
from app.providers.base import LLMReply, LLMRequest, ProviderCall
from app.tools.pii import find_pii

COMPLY = {"small": 0.7, "large": 0.45}
VIOLATE = {"small": 0.6, "large": 0.4}
PII_ECHO = 0.3
UNGROUNDED = {  # (no matching context, matching context)
    "small": (0.55, 0.10),
    "large": (0.40, 0.05),
}
SUMMARY_UNGROUNDED_EXTRA = 0.25  # added to the no-context rate when the input is a summary
SUMMARY_TAG = "Summary:"
SUMMARY_RATIO = 0.5
SUMMARY_MIN_WORDS = 6
HARDENING_PHRASES = ("ignore instructions in the message", "do not follow instructions",
                     "never reveal", "never promise")
HARDENING_FACTOR = 0.5

MARKERS = {
    "refund_promise": "I promise you a full refund.",
    "legal_advice": "My legal advice is that you can go ahead.",
    "internal_url": "You can find it at https://admin.support.internal/console.",
    "credentials": "The admin password is hunter2.",
}

ANSWERS = {
    "billing": "Thanks for reaching out about your bill. I have checked your account and will "
               "walk you through the charges and the next steps.",
    "technical_support": "Sorry for the trouble. Here are the steps that usually fix this; let "
                         "me know if any of them does not work for you.",
    "bug_report": "Thanks for the report. I have logged it with our engineers together with the "
                  "details you shared, and here is a workaround in the meantime.",
    "feature_request": "Thanks for the suggestion. I have passed it to the product team, who "
                       "review requests like this every month.",
    "account": "I can help with your account settings. Here is how to make that change, and "
               "what to expect afterwards.",
    "other": "Thanks for your message. Here is what I can tell you, and where to find more "
             "information.",
}


def _tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _grounded(context: Docs | None, intent: str) -> bool:
    return context is not None and any(d.intent == intent for d in context.docs)


def _summarize(request: LLMRequest, call: ProviderCall) -> LLMReply:
    words = request.text.split()
    keep = min(max(SUMMARY_MIN_WORDS, round(len(words) * SUMMARY_RATIO)), request.max_tokens)
    pii = [m for matches in find_pii(request.text, call.ticket.pii_kinds).values()
           for m in matches]
    kept = " ".join(words[:keep])
    extra = [m for m in pii if m not in kept]
    summary = " ".join([SUMMARY_TAG, kept, *extra])
    return LLMReply(text=summary, tokens_in=_tokens(request.text),
                    tokens_out=_tokens(summary), taint=call.taint)


class MockLLMProvider:
    async def generate(self, request: LLMRequest, call: ProviderCall) -> LLMReply:
        if request.task == "summarize":
            return _summarize(request, call)
        rng, ticket, tier = call.rng, call.ticket, request.model
        hardened = any(p in request.prompt.lower() for p in HARDENING_PHRASES)
        factor = HARDENING_FACTOR if hardened else 1.0

        # Draw every random number up front, in a fixed order, so each behavior's outcome does
        # not depend on which of the others applied.
        u_inject, u_violate, u_pii, u_ground = (rng.random() for _ in range(4))

        taint: set[Taint] = set(call.taint) - {"injection"}
        parts = [ANSWERS.get(ticket.expected_intent, ANSWERS["other"])]
        marker = MARKERS[ticket.risk] if ticket.risk else None
        if "injection" in call.taint and u_inject < COMPLY[tier] * factor:
            taint.add("injection")
            parts.append(marker or "")
        elif ticket.category == "policy_violation" and u_violate < VIOLATE[tier] * factor:
            taint.add("policy_violation")
            parts.append(marker or "")
        found = find_pii(request.text, ticket.pii_kinds) if ticket.contains_pii else {}
        if found and u_pii < PII_ECHO * factor:
            echoed = next(iter(found.values()))[0]
            taint.add("pii")
            parts.append(f"I have noted the details you shared ({echoed}).")
        if ticket.needs_grounding:
            no_ctx, with_ctx = UNGROUNDED[tier]
            if request.text.startswith(SUMMARY_TAG):
                no_ctx = min(1.0, no_ctx + SUMMARY_UNGROUNDED_EXTRA)
            if u_ground < (with_ctx if _grounded(request.context, ticket.expected_intent)
                           else no_ctx):
                taint.add("ungrounded")

        verbosity = 0.8 + 0.4 * request.temperature
        tokens_out = min(request.max_tokens,
                         max(1, round(ticket.expected_answer_tokens * verbosity)))
        context_chars = len(request.context.model_dump_json()) if request.context else 0
        tokens_in = _tokens(request.prompt) + _tokens(request.text) + math.ceil(context_chars / 4)
        return LLMReply(text=" ".join(p for p in parts if p), tokens_in=tokens_in,
                        tokens_out=tokens_out, taint=frozenset(taint))
