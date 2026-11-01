from typing import Any

from app.catalog.definitions.jev import JEV_INTENT_ROUTER, JEV_SAFETY_CHECK
from app.engine.envelope import RunContext, merged_taint
from app.models import NodeResult, PortValue
from app.providers.base import JevQuestion, ProviderFailure
from app.providers.jev_wording import INTENT_INSTRUCTIONS, SAFETY_INSTRUCTIONS
from app.runners.base import measured, missing_input, provider_failed, text

LOW_CONFIDENCE = "route.low_confidence"


class IntentRouterRunner:
    async def run(self, inputs: dict[str, PortValue], params: dict[str, Any],
                  ctx: RunContext) -> NodeResult:
        definition = JEV_INTENT_ROUTER
        if "text" not in inputs:
            return missing_input(definition, "text")
        # The threshold is applied below, after the call, so it stays out of the seed.
        seed_params = {"allowed_intents": params["allowed_intents"]}
        question = JevQuestion(id="intent", kind="choice", prompt=INTENT_INSTRUCTIONS,
                               options=params["allowed_intents"])
        message = inputs["text"]
        try:
            [answer] = await ctx.jev.ask(message.value, [question],
                                         ctx.provider_call(definition.type, seed_params, inputs))
        except ProviderFailure as failure:
            return provider_failed(failure)

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
            **measured(answer.measure, definition, ctx, seed_params, inputs),
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
        question = JevQuestion(id="safety", kind="choice", prompt=SAFETY_INSTRUCTIONS,
                               options=["safe", *params["categories"]])
        message = inputs["text"]
        try:
            [answer] = await ctx.jev.ask(message.value, [question],
                                         ctx.provider_call(definition.type, seed_params, inputs))
        except ProviderFailure as failure:
            return provider_failed(failure)

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
            **measured(answer.measure, definition, ctx, seed_params, inputs),
            decision={"is_safe": is_safe, "confidence": confidence, "flagged": flagged},
        )
