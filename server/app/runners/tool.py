from typing import Any

from app.catalog.definitions.tool import (
    KNOWLEDGE_LOOKUP,
    KNOWLEDGE_LOOKUP_PER_DOC_MS,
    POLICY_ENGINE,
)
from app.engine.envelope import RunContext, merged_taint
from app.models import NodeResult, PortValue
from app.runners.base import latency, missing_input, text
from app.tools.knowledge import lookup
from app.tools.policy import check_policy


class PolicyEngineRunner:
    """Pure rules over the text. It routes but never changes taint: what it misses goes out."""

    async def run(self, inputs: dict[str, PortValue], params: dict[str, Any],
                  ctx: RunContext) -> NodeResult:
        definition = POLICY_ENGINE
        if "text" not in inputs:
            return missing_input(definition, "text")
        message = inputs["text"]
        report = check_policy(message.value, params["rules"], params["blocked_phrases"],
                              params["data_classes"])
        branch = "route.pass" if report.passed else "route.block"
        return NodeResult(
            outputs={
                "passed": PortValue(type="boolean", value=report.passed),
                "report": PortValue(type="json", value=report.model_dump(by_alias=True)),
                branch: text(message.value, merged_taint(inputs)),
            },
            fired_branch=branch,
            latency_ms=latency(definition, ctx, params, inputs),
            cost_usd=definition.cost_model.cost_per_call_usd,
            decision={"passed": report.passed,
                      "violations": [v.rule for v in report.violations]},
        )


class KnowledgeLookupRunner:
    async def run(self, inputs: dict[str, PortValue], params: dict[str, Any],
                  ctx: RunContext) -> NodeResult:
        definition = KNOWLEDGE_LOOKUP
        if "text" not in inputs:
            return missing_input(definition, "text")
        docs = lookup(inputs["text"].value, params["source"], params["top_k"])
        median = definition.cost_model.latency_ms + KNOWLEDGE_LOOKUP_PER_DOC_MS * params["top_k"]
        return NodeResult(
            outputs={"docs": PortValue(type="json", value=docs.model_dump(by_alias=True))},
            latency_ms=latency(definition, ctx, params, inputs, median_ms=median),
            cost_usd=definition.cost_model.cost_per_call_usd,
            decision={"docs": [d.id for d in docs.docs]},
        )
