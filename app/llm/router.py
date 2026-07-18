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

from agents import Agent, ModelSettings, Runner, set_tracing_disabled
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

# Models that rejected the `temperature` parameter (e.g. reasoning models that
# don't expose it). Remembered per process so we skip the wasted attempt on the
# next call instead of 400-ing every time.
_no_temperature: set[str] = set()


async def run_agent(tier: str, build_agent, input_text: str, max_turns: int = 10):
    """build_agent(model, model_settings) -> Agent. Tries primary then fallbacks.

    For each model we first try temperature=0 (reproducible output); if the model
    rejects `temperature` (reasoning models do), we retry the SAME model without
    it and remember that for next time. So temperature-capable models get
    determinism, and models that don't expose it still work.
    """
    tier_cfg = cfg()["routing"][tier]
    specs = [tier_cfg["primary"], *tier_cfg.get("fallbacks", [])]

    last_err: Exception | None = None
    for spec in specs:
        # settings to try, in order: temperature=0 (unless known-unsupported), then plain
        attempts = ([None] if spec in _no_temperature
                    else [ModelSettings(temperature=0.0), None])
        for settings in attempts:
            try:
                agent: Agent = build_agent(resolve_model(spec), settings)
                result = await Runner.run(agent, input_text, max_turns=max_turns)
                try:  # usage accounting (best-effort)
                    u = result.context_wrapper.usage
                    record_usage(_model_name(spec), u.input_tokens, u.output_tokens)
                except Exception:
                    pass
                return result
            except Exception as e:
                if settings is not None and "temperature" in str(e).lower():
                    _no_temperature.add(spec)   # remember; retry same model plain
                    log.info("model %s rejects temperature — retrying without", spec)
                    continue
                log.warning("tier=%s model=%s failed: %s — trying fallback",
                            tier, spec, e)
                last_err = e
                break   # not a temperature issue → move to next model
    raise RuntimeError(f"all models failed for tier '{tier}': {last_err}")
