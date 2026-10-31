from typing import Any

from app.catalog.definitions.llm import LLM_ANSWER_GENERATOR, LLM_SUMMARIZER, TIER_LATENCY_MS
from app.config import LLM_PRICES_PER_1K_USD
from app.engine.envelope import RunContext
from app.models import Docs, NodeResult, PortValue
from app.providers.base import LLMRequest
from app.runners.base import latency, missing_input, text

# Spread of the time to first token, as a fraction of its median.
TTFT_JITTER = 0.2
SUMMARIZER_PROMPT = "Summarize the customer's message in a few words. Keep contact details."


class AnswerGeneratorRunner:
    async def run(self, inputs: dict[str, PortValue], params: dict[str, Any],
                  ctx: RunContext) -> NodeResult:
        definition = LLM_ANSWER_GENERATOR
        if "text" not in inputs:
            return missing_input(definition, "text")
        tier = params["model"]
        seed_params = {key: params[key] for key in ("model", "temperature", "max_tokens", "prompt")}
        context = Docs.model_validate(inputs["context"].value) if "context" in inputs else None
        request = LLMRequest(model=tier, temperature=params["temperature"],
                             max_tokens=params["max_tokens"], prompt=params["prompt"],
                             text=inputs["text"].value, context=context)
        reply = await ctx.llm.generate(request,
                                       ctx.provider_call(definition.type, seed_params, inputs))

        timing = TIER_LATENCY_MS[tier]
        ttft = latency(definition, ctx, seed_params, inputs, median_ms=timing["ttft_ms"],
                       jitter_ms=timing["ttft_ms"] * TTFT_JITTER)
        prices = LLM_PRICES_PER_1K_USD[tier]
        return NodeResult(
            outputs={"text": text(reply.text, reply.taint)},
            latency_ms=ttft + reply.tokens_out * timing["per_token_ms"],
            cost_usd=(reply.tokens_in * prices["in"] + reply.tokens_out * prices["out"]) / 1000,
            tokens_in=reply.tokens_in,
            tokens_out=reply.tokens_out,
            decision={"model": tier, "tokens_out": reply.tokens_out},
        )


class SummarizerRunner:
    async def run(self, inputs: dict[str, PortValue], params: dict[str, Any],
                  ctx: RunContext) -> NodeResult:
        definition = LLM_SUMMARIZER
        if "text" not in inputs:
            return missing_input(definition, "text")
        tier = params["model"]
        request = LLMRequest(model=tier, temperature=0, max_tokens=params["max_tokens"],
                             prompt=SUMMARIZER_PROMPT, text=inputs["text"].value,
                             task="summarize")
        reply = await ctx.llm.generate(request, ctx.provider_call(definition.type, params, inputs))

        timing = TIER_LATENCY_MS[tier]
        ttft = latency(definition, ctx, params, inputs, median_ms=timing["ttft_ms"],
                       jitter_ms=timing["ttft_ms"] * TTFT_JITTER)
        prices = LLM_PRICES_PER_1K_USD[tier]
        return NodeResult(
            outputs={"text": text(reply.text, reply.taint)},
            latency_ms=ttft + reply.tokens_out * timing["per_token_ms"],
            cost_usd=(reply.tokens_in * prices["in"] + reply.tokens_out * prices["out"]) / 1000,
            tokens_in=reply.tokens_in,
            tokens_out=reply.tokens_out,
            decision={"model": tier, "tokens_out": reply.tokens_out},
        )
