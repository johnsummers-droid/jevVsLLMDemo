"""Help panel content for the jev_intent_router node. The rules are in __init__.py."""

from app.catalog.help_text.common import REPEAT_NOTE
from app.models import HelpExample, NodeHelp

JEV_INTENT_ROUTER_HELP = NodeHelp(
    summary="A Jev decision node that reads the message, picks the one intent that fits best "
            "from the list you allow, and sends the message down that intent's branch.",
    placement="Early in the pipeline, usually right after the customer message (or after a "
              "safety check). Each branch leads to the part of the graph that handles that "
              "kind of request.",
    how_it_works=[
        "Jev returns a bounded, typed decision: one intent from the allowed list, with a "
        "probability for each option and a confidence for the winner.",
        "If the confidence is at or above the threshold, the message leaves on "
        "route.<intent>. Below it, the message leaves on route.low_confidence instead.",
        "Exactly one branch fires per request; nodes on the other branches are skipped.",
        "A branch with nothing connected to it drops the requests that take it.",
        REPEAT_NOTE,
    ],
    inputs={
        "text": "The message to classify.",
    },
    params={
        "allowed_intents": "The intents the router may choose from. Each one adds a "
                           "route.<intent> branch. A message whose real intent isn't on the "
                           "list still gets one of the allowed intents: a wrong route.",
        "threshold": "The confidence the router needs to trust its choice. Raise it to send "
                     "more uncertain messages to route.low_confidence; lower it to automate "
                     "more.",
    },
    outputs={
        "intent": "The chosen intent, as a value.",
        "probabilities": "How likely each allowed intent is, as JSON.",
        "confidence": "How sure Jev is, from 0 to 1.",
        "route.*": "Carries {branch} messages.",
        "route.low_confidence": "Carries the message when the router isn't sure enough of any intent.",
    },
    example=HelpExample(
        ticket_id="p-02",
        input_text="How do I reset my password? The reset email never arrives.",
        fired_branch="route.technical_support",
        outputs={
            "intent": "technical_support",
            "confidence": 0.96,
            "probabilities": {"probs": {"technical_support": 0.97, "billing": 0.01,
                                        "bug_report": 0.01, "feature_request": 0.0}},
            "route.technical_support": "How do I reset my password? The reset email never "
                                       "arrives.",
        },
        explanation="Technical support gets 97% of the probability, a confidence of 0.96. That is "
                    "above the default threshold, so the message leaves on "
                    "route.technical_support.",
    ),
    tips=[
        "Connect route.low_confidence to a human review queue so uncertain requests get a "
        "person instead of being dropped.",
        "A wrong route is a wrong answer even if every later step works, so watch the decision "
        "quality metric when you change the threshold.",
    ],
)
