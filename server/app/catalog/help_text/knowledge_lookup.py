"""Help panel content for the knowledge_lookup node. The rules are in __init__.py."""

from app.models import HelpExample, NodeHelp

KNOWLEDGE_LOOKUP_HELP = NodeHelp(
    summary="A tool node that finds help-center articles matching the message, so an LLM can "
            "answer from real product facts instead of guessing.",
    placement="Alongside the LLM: connect the same message to both, and this node's Docs to "
              "the LLM's Context input.",
    how_it_works=[
        "It matches the words in the message against the keywords of every article in the "
        "chosen source.",
        "Articles are ranked by how many keywords match; the best top k are returned.",
        "No AI: the same message always gets the same articles.",
        "More articles take a little longer to fetch and make the LLM read more, which costs "
        "more tokens.",
    ],
    inputs={
        "text": "The message to find articles for.",
    },
    params={
        "source": "Where to search: the FAQ, the knowledge base, or past tickets.",
        "top_k": "How many articles to return at most.",
    },
    outputs={
        "docs": "The best matching help-center articles. Connect to an LLM's Context.",
    },
    example=HelpExample(
        ticket_id="p-07",
        input_text=("Our SSO integration with Okta stopped working after we rotated "
                    "the signing certificate. Users get a SAML assertion error. "
                    "What do we need to update on your side?"),
        params={"top_k": 2},
        outputs={"docs": {"docs": [
            {"id": "kb-sso-cert", "title": "Updating SSO after a certificate rotation",
             "score": 6},
            {"id": "kb-scim", "title": "SCIM provisioning and email case", "score": 1},
        ]}},
        explanation="A question about SSO after a certificate change. The knowledge base has "
                    "a close match (6 keywords) and a weak one (1 keyword).",
    ),
    tips=[
        "Grounding matters most for complex questions that need specific facts; routine "
        "questions do fine without it.",
    ],
)
