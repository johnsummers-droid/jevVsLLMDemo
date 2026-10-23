from typing import Literal, Self

from pydantic import Field, model_validator

from app.models.base import CamelModel
from app.models.params import MultiEnumParam, ParamSpec
from app.models.ports import Port

NodeCategory = Literal["io", "jev", "llm", "tool", "human"]


class CostModel(CamelModel):
    latency_ms: float = Field(ge=0)  # median simulated latency
    latency_jitter_ms: float = Field(default=0, ge=0)
    cost_per_call_usd: float = Field(default=0, ge=0)
    per_token_latency_ms: float | None = Field(default=None, ge=0)  # LLM only
    price_in_per_1k_usd: float | None = Field(default=None, ge=0)  # LLM only
    price_out_per_1k_usd: float | None = Field(default=None, ge=0)
    excluded_from_latency: bool = False  # human review


def _duplicates(ids: list[str]) -> set[str]:
    return {i for i in ids if ids.count(i) > 1}


class NodeDefinition(CamelModel):
    """Serializable node metadata. The run() behavior lives in the server-side registry."""

    type: str
    title: str
    category: NodeCategory
    description: str
    inputs: list[Port]
    outputs: list[Port]
    params: list[ParamSpec]
    cost_model: CostModel
    max_fan_out: int = Field(default=4, ge=1)
    # Optional inputs of which at least one must be connected (e.g. an escalation gate needs
    # a confidence, score or flag signal). Checked by the validator as GATE_NEEDS_SIGNAL.
    requires_one_of: list[str] = Field(default_factory=list)
    is_source: bool = False
    is_sink: bool = False
    mvp: bool = True

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if dup := _duplicates([p.id for p in self.inputs]):
            raise ValueError(f"duplicate input port ids: {sorted(dup)}")
        if dup := _duplicates([p.id for p in self.outputs]):
            raise ValueError(f"duplicate output port ids: {sorted(dup)}")
        if dup := _duplicates([p.key for p in self.params]):
            raise ValueError(f"duplicate param keys: {sorted(dup)}")
        for port in self.inputs:
            if port.branch or port.dynamic_from_param:
                raise ValueError(f"input {port.id!r}: branch/dynamic ports are outputs only")
        inputs = {p.id: p for p in self.inputs}
        for port_id in self.requires_one_of:
            if port_id not in inputs or inputs[port_id].required:
                raise ValueError(f"requires_one_of: {port_id!r} must be an optional input")
        params = {p.key: p for p in self.params}
        for port in self.outputs:
            if port.multi:
                raise ValueError(f"output {port.id!r}: multi applies to inputs only")
            if port.dynamic_from_param is not None:
                if not port.branch:
                    raise ValueError(f"output {port.id!r}: dynamic ports must be branch ports")
                if not isinstance(params.get(port.dynamic_from_param), MultiEnumParam):
                    raise ValueError(
                        f"output {port.id!r}: dynamic_from_param must name a multi_enum param"
                    )
        if self.is_source and self.inputs:
            raise ValueError("source nodes have no inputs")
        if self.is_sink and self.outputs:
            raise ValueError("sink nodes have no outputs")
        if self.is_source and self.is_sink:
            raise ValueError("a node cannot be both source and sink")
        return self
