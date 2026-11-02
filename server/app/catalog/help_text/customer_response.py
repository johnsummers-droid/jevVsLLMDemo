"""Help panel content for the customer_response node. The rules are in __init__.py."""

from app.models import NodeHelp

CUSTOMER_RESPONSE_HELP = NodeHelp(
    summary="The end of every pipeline: whatever arrives here is sent to the customer.",
    placement="Exactly one per graph, on the far right. Connect every branch that should "
              "answer the customer to it.",
    how_it_works=[
        "A request that reaches this node is answered. It counts as automated, or as "
        "escalated if it passed through a human review queue on the way.",
        "A request that ends on an unconnected safety-check unsafe branch or policy block "
        "branch counts as blocked. One that ends on any other unconnected branch is dropped: "
        "the customer gets no answer.",
        "If what arrives is unsafe, it has been sent anyway: that counts as an unsafe "
        "release.",
        "When several branches can reach it on the same request, the first to arrive wins.",
    ],
    inputs={"text": "The answer to send. Several branches can connect to it."},
    params={
        "channel": "How the answer is delivered: email or chat. Display only for now.",
        "sla_ms": "The response-time target to display. It doesn't change the run.",
    },
    tips=[
        "Look at the outcome metrics after a run: dropped and unsafe requests both point to "
        "a branch that needs attention.",
    ],
)
