from app.catalog.help import HUMAN_REVIEW_QUEUE_HELP
from app.models import CostModel, IntParam, NodeDefinition, Port

HUMAN_REVIEW_QUEUE = NodeDefinition(
    type="human_review_queue",
    title="Human review queue",
    category="human",
    description="A person reviews the case. Slow and costly, but almost always safe. "
                "Counts as escalated.",
    inputs=[
        Port(id="text", label="Text", type="text", multi=True),
        Port(id="context", label="Context", type="json", required=False),
    ],
    outputs=[Port(id="text", label="Text", type="text")],
    params=[
        IntParam(key="capacity", label="Reviewers", default=2, min=1, max=10),
        IntParam(key="reviewer_latency_s", label="Review time (s)", default=120, min=30, max=600),
    ],
    # $2.00 per review is a mock default; it moves to server config with the other prices.
    help=HUMAN_REVIEW_QUEUE_HELP,
    cost_model=CostModel(latency_ms=120_000, cost_per_call_usd=2.00, excluded_from_latency=True),
)

DEFINITIONS = [HUMAN_REVIEW_QUEUE]
