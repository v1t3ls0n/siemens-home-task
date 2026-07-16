"""Model routing + usage/cost tracking.

Pipeline stages ask for a TIER ("light"/"heavy"), never a concrete model.
config.yaml maps tiers to a primary model and fallbacks across providers:

  openai:gpt-5-mini        -> OpenAI Responses API (automatic prompt caching)
  anthropic:claude-...     -> via LiteLLM
  ollama:qwen2.5:7b        -> LOCAL model via Ollama (zero cost)

run_agent(tier, ...) tries the primary, then each fallback, so an outage or
rate-limit on one provider degrades gracefully instead of failing the request.
Every call's token usage is recorded and priced for the /api/usage report.
"""

import logging
import os
import threading
from typing import Any

from agents import Agent, Runner, set_tracing_disabled
from agents.extensions.models.litellm_model import LitellmModel

from app.config import OLLAMA_BASE_URL, cfg

log = logging.getLogger("router")

if os.environ.get("AGENTS_TRACING", "0") != "1":
    set_tracing_disabled(True)


def resolve_model(spec: str) -> Any:
    """'provider:model' -> something Agent(model=...) accepts."""
    provider, _, model = spec.partition(":")
    if provider == "openai":
        return model                                # native Responses API
    if provider == "anthropic":
        return LitellmModel(model=f"anthropic/{model}")
    if provider == "ollama":
        return LitellmModel(
            model=f"ollama_chat/{model}", base_url=OLLAMA_BASE_URL
        )
    raise ValueError(f"unknown provider in model spec: {spec}")


def _model_name(spec: str) -> str:
    return spec.partition(":")[2]


# --------------------------------------------------------------------------
# Usage / cost tracking
# --------------------------------------------------------------------------

_usage_lock = threading.Lock()
_usage: dict[str, dict[str, float]] = {}   # model -> {input, output, cost, calls}


def record_usage(model: str, input_tokens: int, output_tokens: int) -> None:
    prices = cfg().get("prices", {}).get(model, {"input": 0, "output": 0})
    cost = (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1e6
    with _usage_lock:
        u = _usage.setdefault(model, {"input": 0, "output": 0, "cost": 0.0, "calls": 0})
        u["input"] += input_tokens
        u["output"] += output_tokens
        u["cost"] += cost
        u["calls"] += 1


def usage_report() -> dict:
    with _usage_lock:
        total = sum(u["cost"] for u in _usage.values())
        return {"models": dict(_usage), "total_cost_usd": round(total, 4)}


# --------------------------------------------------------------------------
# Tier-routed agent execution with fallback chain
# --------------------------------------------------------------------------

async def run_agent(tier: str, build_agent, input_text: str, max_turns: int = 10):
    """build_agent(model) -> Agent. Tries primary then fallbacks."""
    tier_cfg = cfg()["routing"][tier]
    specs = [tier_cfg["primary"], *tier_cfg.get("fallbacks", [])]

    last_err: Exception | None = None
    for spec in specs:
        try:
            agent: Agent = build_agent(resolve_model(spec))
            result = await Runner.run(agent, input_text, max_turns=max_turns)
            try:  # usage accounting (best-effort)
                u = result.context_wrapper.usage
                record_usage(_model_name(spec), u.input_tokens, u.output_tokens)
            except Exception:
                pass
            return result
        except Exception as e:  # provider down / rate limit / model error
            log.warning("tier=%s model=%s failed: %s — trying fallback", tier, spec, e)
            last_err = e
    raise RuntimeError(f"all models failed for tier '{tier}': {last_err}")
