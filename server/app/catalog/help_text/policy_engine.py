"""Help panel content for the policy_engine node. The rules are in __init__.py."""

from app.models import HelpExample, NodeHelp

POLICY_ENGINE_HELP = NodeHelp(
    summary="A tool node that checks text against fixed rules before it goes out, and passes "
            "or blocks it. No AI: the same text always gets the same verdict.",
    placement="After the LLM, before the customer response. Connect route.pass to the "
              "response and route.block to a human review queue (or leave it unconnected to "
              "block).",
    how_it_works=[
        "Every enabled rule, every blocked phrase and every selected data class is checked "
        "against the text.",
        "Any match blocks the text: it leaves on route.block, and the report lists each "
        "match. No match: it leaves on route.pass.",
        "The text itself is never changed; only its route.",
        "Rules look for patterns, so they catch the wording they were written for and can "
        "miss the same idea phrased differently.",
        "Blocked text on an unconnected route.block counts as blocked, not dropped.",
    ],
    inputs={
        "text": "The text to check, usually the LLM's answer.",
        "context": "Optional; not used by the rules.",
    },
    params={
        "rules": "Built-in rules. no_refund_promises: promising or guaranteeing a refund. "
                 "no_legal_advice: giving a legal opinion. no_internal_urls: links to internal "
                 "or admin sites. no_credentials: stating a password, API key, secret or "
                 "token.",
        "blocked_phrases": "Your own phrases. Each is matched anywhere in the text, ignoring "
                           "case.",
        "data_classes": "Personal data that must not go out: email addresses, phone numbers, "
                        "card numbers, social security numbers.",
    },
    outputs={
        "passed": "True when nothing matched.",
        "report": "Every match: which rule and the text it matched, as JSON.",
        "route.pass": "Text that passed.",
        "route.block": "Text that was blocked.",
    },
    example=HelpExample(
        ticket_id="p-01",
        input_text="Good news: we guarantee a refund if the new plan does not suit you.",
        fired_branch="route.block",
        outputs={
            "passed": False,
            "report": {"passed": False, "violations": [
                {"rule": "no_refund_promises", "match": "guarantee a refund"}]},
        },
        explanation="The answer guarantees a refund, which the default rule forbids, so it "
                    "leaves on route.block with the match in the report.",
    ),
    tips=[
        "Only one rule is on by default. Think about which kinds of answer you never want to "
        "send, and turn on the rules that cover them.",
        "It's free and fast, so it costs almost nothing to put one in front of the response.",
    ],
)
