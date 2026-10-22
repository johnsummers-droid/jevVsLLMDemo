from app.models import CostModel, MultiEnumParam, NodeDefinition, NumberParam, Port

INTENTS = ["billing", "technical_support", "bug_report", "feature_request", "account", "other"]

JEV_INTENT_ROUTER = NodeDefinition(
    type="jev_intent_router",
    title="Jev intent router",
    category="jev",
    description="Classifies the message into one allowed intent and routes it. "
                "Low-confidence decisions go to their own branch.",
    inputs=[Port(id="text", label="Text", type="text", multi=True)],
    outputs=[
        Port(id="intent", label="Intent", type="enum", enum_values=INTENTS),
        Port(id="probabilities", label="Probabilities", type="json",
             json_schema_ref="Distribution"),
        Port(id="confidence", label="Confidence", type="probability"),
        Port(id="route.*", label="Route", type="text", branch=True,
             dynamic_from_param="allowed_intents"),
        Port(id="route.low_confidence", label="Low confidence", type="text", branch=True),
    ],
    params=[
        MultiEnumParam(key="allowed_intents", label="Allowed intents", default=INTENTS[:4],
                       options=INTENTS),
        NumberParam(key="threshold", label="Confidence threshold", default=0.50, min=0, max=1,
                    help="Below this confidence the request takes route.low_confidence."),
    ],
    cost_model=CostModel(latency_ms=40, latency_jitter_ms=15, cost_per_call_usd=0.0002),
)

JEV_SAFETY_CHECK = NodeDefinition(
    type="jev_safety_check",
    title="Jev safety check",
    category="jev",
    description="Flags prompt injection, abuse and other risky messages for the enabled "
                "categories.",
    inputs=[Port(id="text", label="Text", type="text", multi=True)],
    outputs=[
        Port(id="is_safe", label="Is safe", type="boolean"),
        Port(id="confidence", label="Confidence", type="probability"),
        Port(id="categories", label="Categories", type="json"),
        Port(id="route.safe", label="Safe", type="text", branch=True),
        Port(id="route.unsafe", label="Unsafe", type="text", branch=True),
    ],
    params=[
        MultiEnumParam(key="categories", label="Categories",
                       default=["prompt_injection", "abuse"],
                       options=["prompt_injection", "abuse", "fraud", "pii_request",
                                "self_harm"]),
        NumberParam(key="threshold", label="Threshold", default=0.50, min=0, max=1),
    ],
    cost_model=CostModel(latency_ms=30, latency_jitter_ms=10, cost_per_call_usd=0.0002),
)

DEFINITIONS = [JEV_INTENT_ROUTER, JEV_SAFETY_CHECK]
