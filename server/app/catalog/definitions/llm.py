from app.models import CostModel, EnumParam, IntParam, NodeDefinition, NumberParam, Port, TextParam

# Per-tier latency (plan1.txt 3b). The catalog's CostModel shows the default ("large")
# tier; runners read this table. Token prices per tier come from server config (T4).
TIER_LATENCY_MS = {
    "small": {"ttft_ms": 150, "per_token_ms": 4},
    "large": {"ttft_ms": 350, "per_token_ms": 10},
}

LLM_ANSWER_GENERATOR = NodeDefinition(
    type="llm_answer_generator",
    title="LLM answer generator",
    category="llm",
    description="Writes a reply to the customer, optionally grounded in retrieved docs.",
    inputs=[
        Port(id="text", label="Text", type="text", multi=True),
        Port(id="context", label="Context", type="json", json_schema_ref="Docs",
             required=False),
    ],
    outputs=[Port(id="text", label="Text", type="text")],
    params=[
        EnumParam(key="model", label="Model tier", default="large", options=["small", "large"]),
        NumberParam(key="temperature", label="Temperature", default=0.7, min=0, max=1),
        IntParam(key="max_tokens", label="Max tokens", default=512, min=64, max=1024),
        TextParam(key="prompt", label="System prompt",
                  default="You are a helpful support agent.", max_len=500),
    ],
    cost_model=CostModel(
        latency_ms=TIER_LATENCY_MS["large"]["ttft_ms"],
        per_token_latency_ms=TIER_LATENCY_MS["large"]["per_token_ms"],
    ),
)

LLM_SUMMARIZER = NodeDefinition(
    type="llm_summarizer",
    title="LLM summarizer",
    category="llm",
    description="Shortens the message so later LLM calls read less. Details can get lost.",
    inputs=[Port(id="text", label="Text", type="text", multi=True)],
    outputs=[Port(id="text", label="Text", type="text")],
    params=[
        EnumParam(key="model", label="Model tier", default="small", options=["small", "large"]),
        IntParam(key="max_tokens", label="Max tokens", default=128, min=32, max=256),
    ],
    cost_model=CostModel(
        latency_ms=TIER_LATENCY_MS["small"]["ttft_ms"],
        per_token_latency_ms=TIER_LATENCY_MS["small"]["per_token_ms"],
    ),
    mvp=False,
)

DEFINITIONS = [LLM_ANSWER_GENERATOR, LLM_SUMMARIZER]
