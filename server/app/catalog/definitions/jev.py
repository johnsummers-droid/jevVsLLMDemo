from app.models import (
    CostModel,
    EnumParam,
    IntParam,
    MultiEnumParam,
    NodeDefinition,
    NumberParam,
    Port,
)

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

URGENCY_RANGE = (1, 5)
# rubric_levels "3" reports only these levels (the closest one, rounding up).
RUBRIC_LEVELS = {"3": [1, 3, 5], "5": [1, 2, 3, 4, 5]}

JEV_URGENCY_SCORER = NodeDefinition(
    type="jev_urgency_scorer",
    title="Jev urgency scorer",
    category="jev",
    description="Scores how urgent the message is, from 1 (can wait) to 5 (drop everything).",
    inputs=[Port(id="text", label="Text", type="text", multi=True)],
    outputs=[
        Port(id="score", label="Urgency", type="score", score_range=URGENCY_RANGE),
        Port(id="confidence", label="Confidence", type="probability"),
    ],
    params=[
        EnumParam(key="rubric_levels", label="Rubric levels", default="5",
                  options=list(RUBRIC_LEVELS),
                  help="3 levels report only 1, 3 or 5."),
    ],
    cost_model=CostModel(latency_ms=35, latency_jitter_ms=10, cost_per_call_usd=0.0002),
    mvp=False,
)

GATE_DECISIONS = ["auto", "human", "fallback"]

JEV_ESCALATION_GATE = NodeDefinition(
    type="jev_escalation_gate",
    title="Jev escalation gate",
    category="jev",
    description="Decides from the signals it gets whether the request is handled automatically "
                "or goes to a human. Connect at least one of confidence, urgency or flag.",
    inputs=[
        Port(id="text", label="Text", type="text"),
        Port(id="confidence", label="Confidence", type="probability", required=False),
        Port(id="score", label="Urgency", type="score", score_range=URGENCY_RANGE,
             required=False),
        Port(id="flag", label="Flag", type="boolean", required=False),
    ],
    outputs=[
        Port(id="decision", label="Decision", type="enum", enum_values=GATE_DECISIONS),
        Port(id="confidence", label="Confidence", type="probability"),
        Port(id="route.auto", label="Auto", type="text", branch=True),
        Port(id="route.human", label="Human", type="text", branch=True),
        Port(id="route.fallback", label="Fallback", type="text", branch=True),
    ],
    params=[
        NumberParam(key="min_confidence", label="Min confidence", default=0.70, min=0, max=1,
                    help="Below this confidence the request goes to route.human."),
        IntParam(key="max_auto_urgency", label="Max automatic urgency", default=3, min=1, max=5,
                 help="A higher urgency goes to route.human."),
        EnumParam(key="flag_routes_to", label="Flag routes to", default="human",
                  options=["human", "fallback"],
                  help="Where a request goes when the flag input is true."),
        EnumParam(key="fallback_route", label="No signal routes to", default="human",
                  options=["human", "auto"],
                  help="Where a request goes when none of its signals arrived."),
    ],
    cost_model=CostModel(latency_ms=20, latency_jitter_ms=5, cost_per_call_usd=0.0001),
    requires_one_of=["confidence", "score", "flag"],
    mvp=False,
)

DEFINITIONS = [JEV_INTENT_ROUTER, JEV_SAFETY_CHECK, JEV_URGENCY_SCORER, JEV_ESCALATION_GATE]
