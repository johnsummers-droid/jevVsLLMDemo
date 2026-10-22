from app.models import CostModel, MultiEnumParam, NodeDefinition, Port, StringListParam

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

DEFINITIONS = [POLICY_ENGINE]
