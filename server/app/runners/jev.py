from typing import Any

from app.catalog.definitions.jev import (
    JEV_ESCALATION_GATE,
    JEV_INTENT_ROUTER,
    JEV_SAFETY_CHECK,
    JEV_URGENCY_SCORER,
    RUBRIC_LEVELS,
)
from app.engine.envelope import RunContext, merged_taint
from app.models import NodeResult, PortValue
from app.providers.base import JevQuestion
from app.runners.base import latency, missing_input, text

LOW_CONFIDENCE = "route.low_confidence"


class IntentRouterRunner:
    async def run(self, inputs: dict[str, PortValue], params: dict[str, Any],
                  ctx: RunContext) -> NodeResult:
        definition = JEV_INTENT_ROUTER
        if "text" not in inputs:
            return missing_input(definition, "text")
        # The threshold is applied below, after the call, so it stays out of the seed.
        seed_params = {"allowed_intents": params["allowed_intents"]}
        question = JevQuestion(id="intent", kind="choice", prompt="Which intent fits best?",
                               options=params["allowed_intents"])
        message = inputs["text"]
        [answer] = await ctx.jev.ask(message.value, [question],
                                     ctx.provider_call(definition.type, seed_params, inputs))

        taint = merged_taint(inputs)
        if answer.confidence < params["threshold"]:
            branch = LOW_CONFIDENCE
        else:
            branch = f"route.{answer.value}"
            if answer.value != ctx.ticket.expected_intent:
                taint.add("misrouted")
        return NodeResult(
            outputs={
                "intent": PortValue(type="enum", value=answer.value),
                "probabilities": PortValue(type="json",
                                           value=answer.probabilities.model_dump(by_alias=True)),
                "confidence": PortValue(type="probability", value=answer.confidence),
                branch: text(message.value, taint),
            },
            fired_branch=branch,
            latency_ms=latency(definition, ctx, seed_params, inputs),
            cost_usd=definition.cost_model.cost_per_call_usd,
            decision={"intent": answer.value, "confidence": answer.confidence},
        )


class SafetyCheckRunner:
    """Flags the message when p(unsafe) >= threshold.

    Taint is never stripped: a missed injection keeps its "injection" taint on route.safe, and a
    flagged message keeps it on route.unsafe until a human clears it.
    """

    async def run(self, inputs: dict[str, PortValue], params: dict[str, Any],
                  ctx: RunContext) -> NodeResult:
        definition = JEV_SAFETY_CHECK
        if "text" not in inputs:
            return missing_input(definition, "text")
        seed_params = {"categories": params["categories"]}
        question = JevQuestion(id="safety", kind="choice", prompt="Is this message safe?",
                               options=["safe", *params["categories"]])
        message = inputs["text"]
        [answer] = await ctx.jev.ask(message.value, [question],
                                     ctx.provider_call(definition.type, seed_params, inputs))

        probs = answer.probabilities.probs
        p_unsafe = 1 - probs["safe"]
        is_safe = p_unsafe < params["threshold"]
        flagged = [] if is_safe else [max(params["categories"], key=lambda c: probs[c])]
        branch = "route.safe" if is_safe else "route.unsafe"
        confidence = 1 - p_unsafe if is_safe else p_unsafe
        return NodeResult(
            outputs={
                "is_safe": PortValue(type="boolean", value=is_safe),
                "confidence": PortValue(type="probability", value=confidence),
                "categories": PortValue(type="json", value={
                    "flagged": flagged, "scores": {c: probs[c] for c in params["categories"]}}),
                branch: text(message.value, merged_taint(inputs)),
            },
            fired_branch=branch,
            latency_ms=latency(definition, ctx, seed_params, inputs),
            cost_usd=definition.cost_model.cost_per_call_usd,
            decision={"is_safe": is_safe, "confidence": confidence, "flagged": flagged},
        )


class UrgencyScorerRunner:
    async def run(self, inputs: dict[str, PortValue], params: dict[str, Any],
                  ctx: RunContext) -> NodeResult:
        definition = JEV_URGENCY_SCORER
        if "text" not in inputs:
            return missing_input(definition, "text")
        levels = [str(level) for level in RUBRIC_LEVELS[params["rubric_levels"]]]
        question = JevQuestion(id="urgency", kind="choice", prompt="How urgent is this?",
                               options=levels)
        [answer] = await ctx.jev.ask(inputs["text"].value, [question],
                                     ctx.provider_call(definition.type, params, inputs))
        score = int(answer.value)
        return NodeResult(
            outputs={
                "score": PortValue(type="score", value=score),
                "confidence": PortValue(type="probability", value=answer.confidence),
            },
            latency_ms=latency(definition, ctx, params, inputs),
            cost_usd=definition.cost_model.cost_per_call_usd,
            decision={"urgency": score, "confidence": answer.confidence},
        )


class EscalationGateRunner:
    """A fixed rule over the signals that arrived: flag first, then confidence, then urgency.

    With no live signal (each one sat on a branch that did not fire) it takes fallback_route.
    """

    async def run(self, inputs: dict[str, PortValue], params: dict[str, Any],
                  ctx: RunContext) -> NodeResult:
        definition = JEV_ESCALATION_GATE
        if "text" not in inputs:
            return missing_input(definition, "text")
        flag, confidence, score = (inputs[k].value if k in inputs else None
                                   for k in ("flag", "confidence", "score"))
        if flag is None and confidence is None and score is None:
            decision, reason = params["fallback_route"], "no_signal"
        elif flag:
            decision, reason = params["flag_routes_to"], "flag"
        elif confidence is not None and confidence < params["min_confidence"]:
            decision, reason = "human", "low_confidence"
        elif score is not None and score > params["max_auto_urgency"]:
            decision, reason = "human", "urgent"
        else:
            decision, reason = "auto", "ok"
        branch = f"route.{decision}"
        own_confidence = 1.0 if confidence is None else confidence
        return NodeResult(
            outputs={
                "decision": PortValue(type="enum", value=decision),
                "confidence": PortValue(type="probability", value=own_confidence),
                branch: text(inputs["text"].value, inputs["text"].taint),
            },
            fired_branch=branch,
            latency_ms=latency(definition, ctx, params, inputs),
            cost_usd=definition.cost_model.cost_per_call_usd,
            decision={"decision": decision, "reason": reason},
        )
