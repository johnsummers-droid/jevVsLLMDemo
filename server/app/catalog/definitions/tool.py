from app.models import (
    CostModel,
    EnumParam,
    IntParam,
    MultiEnumParam,
    NodeDefinition,
    Port,
    StringListParam,
)

POLICY_ENGINE = NodeDefinition(
    type="policy_engine",
    title="Policy engine",
    category="tool",
    description="Deterministic regex and phrase rules. Passes or blocks the text.",
    inputs=[
        Port(id="text", label="Text", type="text", multi=True),
        Port(id="context", label="Context", type="json", required=False),
    ],
    outputs=[
        Port(id="passed", label="Passed", type="boolean"),
        Port(id="report", label="Report", type="json", json_schema_ref="PolicyReport"),
        Port(id="route.pass", label="Pass", type="text", branch=True),
        Port(id="route.block", label="Block", type="text", branch=True),
    ],
    params=[
        MultiEnumParam(key="rules", label="Rules", default=["no_refund_promises"],
                       options=["no_refund_promises", "no_legal_advice", "no_internal_urls",
                                "no_credentials"],
                       min_selected=0),
        StringListParam(key="blocked_phrases", label="Blocked phrases", default=[]),
        MultiEnumParam(key="data_classes", label="Data classes", default=[],
                       options=["email", "phone", "card_number", "ssn"], min_selected=0),
    ],
    cost_model=CostModel(latency_ms=10, latency_jitter_ms=3),
)

# Latency is 25 ms + 5 ms per requested doc (plan1.txt 3b); the runner adds the per-doc part.
KNOWLEDGE_LOOKUP_PER_DOC_MS = 5

KNOWLEDGE_LOOKUP = NodeDefinition(
    type="knowledge_lookup",
    title="Knowledge lookup",
    category="tool",
    description="Finds help-center articles that match the message, to ground an LLM answer.",
    inputs=[Port(id="text", label="Text", type="text", multi=True)],
    outputs=[Port(id="docs", label="Docs", type="json", json_schema_ref="Docs")],
    params=[
        EnumParam(key="source", label="Source", default="kb", options=["faq", "kb", "tickets"]),
        IntParam(key="top_k", label="Top k", default=3, min=1, max=10),
    ],
    cost_model=CostModel(latency_ms=25, latency_jitter_ms=5, cost_per_call_usd=0.00001),
)

PII_REDACTOR = NodeDefinition(
    type="pii_redactor",
    title="PII redactor",
    category="tool",
    description="Replaces personal data (emails, phone numbers, ...) in the text with "
                "placeholders.",
    inputs=[Port(id="text", label="Text", type="text", multi=True)],
    outputs=[Port(id="text", label="Text", type="text")],
    params=[
        MultiEnumParam(key="entity_types", label="Entity types",
                       default=["email", "phone", "card_number"],
                       options=["email", "phone", "card_number", "ssn"], min_selected=0),
    ],
    cost_model=CostModel(latency_ms=8),
    mvp=False,
)

DEFINITIONS = [POLICY_ENGINE, KNOWLEDGE_LOOKUP, PII_REDACTOR]
