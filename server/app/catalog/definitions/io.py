from app.models import CostModel, EnumParam, IntParam, NodeDefinition, NumberParam, Port

CUSTOMER_MESSAGE = NodeDefinition(
    type="customer_message",
    title="Customer message",
    category="io",
    description="Entry point: emits one support ticket per request.",
    inputs=[],
    outputs=[
        Port(id="text", label="Text", type="text"),
        Port(id="meta", label="Meta", type="json", json_schema_ref="TicketMeta"),
    ],
    params=[
        # All three are overridden by the facilitator in official runs (plan1.txt D9).
        EnumParam(key="traffic_mix", label="Traffic mix", default="realistic",
                  options=["realistic", "routine_heavy", "adversarial"]),
        EnumParam(key="language", label="Language", default="en", options=["en"]),
        NumberParam(key="attack_rate", label="Attack rate", default=0.10, min=0, max=0.5),
    ],
    cost_model=CostModel(latency_ms=0),
    is_source=True,
)

CUSTOMER_RESPONSE = NodeDefinition(
    type="customer_response",
    title="Customer response",
    category="io",
    description="Exit point: whatever arrives here is sent to the customer.",
    inputs=[Port(id="text", label="Text", type="text", multi=True)],
    outputs=[],
    params=[
        EnumParam(key="channel", label="Channel", default="chat", options=["email", "chat"]),
        IntParam(key="sla_ms", label="SLA (ms, display only)", default=800, min=100, max=10_000),
    ],
    cost_model=CostModel(latency_ms=0),
    is_sink=True,
)

DEFINITIONS = [CUSTOMER_MESSAGE, CUSTOMER_RESPONSE]
