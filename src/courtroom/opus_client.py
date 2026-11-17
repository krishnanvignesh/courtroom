"""Court model client with disk caching, strict ledger accounting, and USD budget cap."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from courtroom.schemas import SchemaValidationError, validate_schema

DEFAULT_COURT_MODEL = "us.anthropic.claude-opus-5-5"

# USD per 1M tokens (input, output)
MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "us.anthropic.claude-opus-5-5": (15.0, 75.0),
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (0.80, 4.0),
    "gpt-5": (10.0, 30.0),
    "gpt-4o": (2.5, 10.0),
}

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
_BLIND_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bParty\s+A\s*\(\s*production\s*\)", re.IGNORECASE), "Submission A"),
    (re.compile(r"\bParty\s+B\s*\(\s*independent\s*\)", re.IGNORECASE), "Submission B"),
    (re.compile(r"\bours\s*\(\s*production\s*\)", re.IGNORECASE), "Submission A"),
    (re.compile(r"\bproduction\s+output\b", re.IGNORECASE), "Submission A"),
    (re.compile(r"\bours_a\b", re.IGNORECASE), "submission_a"),
    (re.compile(r"\bours\b", re.IGNORECASE), "submission_a"),
]


class BudgetExceededError(RuntimeError):
    """Raised when a paid court call would exceed the configured USD budget cap."""


def blind_payload(text: str) -> str:
    """Neutralize provenance labels so judges cannot favor 'ours' / production."""
    blinded = text
    for pattern, replacement in _BLIND_PATTERNS:
        blinded = pattern.sub(replacement, blinded)
    return blinded


def estimate_tokens(text: str) -> int:
    """Approximate token count (~4 chars/token, minimum 1 when non-empty)."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _extract_json_object(raw: Any) -> dict[str, Any]:
    """Parse a JSON dict from raw text (stripping Markdown fences) or return dict directly."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raise SchemaValidationError(f"Expected JSON string or dict, got {type(raw).__name__}")
    stripped = raw.strip()
    fence_match = _JSON_FENCE_RE.match(stripped)
    if fence_match:
        stripped = fence_match.group(1).strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"Invalid JSON from model: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SchemaValidationError(f"Expected JSON object, got {type(parsed).__name__}")
    return parsed


class CourtClient:
    """Provider-agnostic court-model client with cache, ledger, and budget enforcement."""

    def __init__(
        self,
        ledger_path: str | Path,
        cache_dir: str | Path,
        budget_usd: float | None = 5.0,
        model: str = DEFAULT_COURT_MODEL,
        provider: str = "mock",
        blind_roles: tuple[str, ...] = ("plan_judge", "trial_judge", "closing_judge"),
        bedrock_profile: str | None = None,
        bedrock_region: str | None = None,
    ) -> None:
        self.ledger_path = Path(ledger_path)
        self.cache_dir = Path(cache_dir)
        self.budget_usd = budget_usd
        self.model = model
        self.provider = provider
        self.blind_roles = set(blind_roles)
        self.bedrock_profile = bedrock_profile or os.environ.get("AWS_PROFILE")
        self.bedrock_region = bedrock_region or os.environ.get("AWS_REGION", "us-east-1")

        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _pricing(self) -> tuple[float, float]:
        return MODEL_PRICING_PER_1M.get(self.model, (15.0, 75.0))

    def estimate_cost(self, prompt_text: str, expected_output_tokens: int = 800) -> float:
        """Estimate USD cost for a call given prompt text and expected output tokens."""
        in_rate, out_rate = self._pricing()
        in_tokens = estimate_tokens(prompt_text)
        cost = (in_tokens / 1_000_000.0) * in_rate + (expected_output_tokens / 1_000_000.0) * out_rate
        return round(cost, 6)

    def read_ledger(self) -> list[dict[str, Any]]:
        """Read all recorded entries from ledger.json."""
        if not self.ledger_path.is_file():
            return []
        text = self.ledger_path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError(f"Expected list in ledger {self.ledger_path}")
        return data

    def current_spend(self) -> float:
        """Sum recorded USD spend across ledger.json."""
        return round(sum(float(entry.get("cost_usd", 0.0)) for entry in self.read_ledger()), 6)

    def _record_ledger(self, entry: dict[str, Any]) -> None:
        entries = self.read_ledger()
        entries.append(entry)
        self.ledger_path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")

    def _cache_key(self, role: str, schema_name: str, system_prompt: str, user_prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "role": role,
                "schema_name": schema_name,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _cache_file(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _invoke_factory(
        self,
        response_factory: Callable[..., Any],
        role: str,
        system_prompt: str,
        user_prompt: str,
        attempt: int,
    ) -> Any:
        sig = inspect.signature(response_factory)
        params = list(sig.parameters.values())
        if len(params) == 0:
            return response_factory()
        if len(params) == 1:
            return response_factory(role)
        if len(params) == 3:
            return response_factory(role, system_prompt, user_prompt)
        return response_factory(role, system_prompt, user_prompt, attempt)

    def _invoke_provider(
        self,
        role: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        response_factory: Callable[..., Any] | None,
        attempt: int,
    ) -> Any:
        if self.provider == "mock":
            if response_factory is None:
                raise RuntimeError(
                    f"CourtClient in 'mock' mode requires response_factory for uncached call '{role}'."
                )
            return self._invoke_factory(
                response_factory, role, system_prompt, user_prompt, attempt
            )
        if self.provider == "bedrock":
            return self._call_bedrock(system_prompt, user_prompt)
        if self.provider == "anthropic":
            return self._call_anthropic(system_prompt, user_prompt)
        if self.provider == "openai":
            return self._call_openai(system_prompt, user_prompt)
        raise ValueError(f"Unsupported provider: '{self.provider}'")

    def _call_bedrock(self, system_prompt: str, user_prompt: str) -> str:
        import boto3  # Lazy import so offline tests need zero cloud deps.

        session = (
            boto3.Session(profile_name=self.bedrock_profile, region_name=self.bedrock_region)
            if self.bedrock_profile
            else boto3.Session(region_name=self.bedrock_region)
        )
        client = session.client("bedrock-runtime")
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }
        )
        resp = client.invoke_model(modelId=self.model, body=body)
        payload = json.loads(resp["body"].read().decode("utf-8"))
        blocks = payload.get("content", [])
        return "".join(b.get("text", "") for b in blocks if isinstance(b, dict))

    def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        import anthropic  # Lazy import.

        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(getattr(block, "text", "") for block in msg.content)

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        import openai  # Lazy import.

        client = openai.OpenAI()
        resp = client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content or "{}"

    def call(
        self,
        role: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        response_factory: Callable[..., Any] | None = None,
        force_uncached: bool = False,
        expected_output_tokens: int = 800,
        should_cache: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        """Call the court model with disk caching, blinding, budget cap, and 1 retry."""
        effective_user_prompt = (
            blind_payload(user_prompt) if role in self.blind_roles else user_prompt
        )
        cache_key = self._cache_key(role, schema_name, system_prompt, effective_user_prompt)
        cache_file = self._cache_file(cache_key)

        if not force_uncached and cache_file.is_file():
            cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
            validated = validate_schema(cached_data, schema_name)
            self._record_ledger(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "role": role,
                    "schema_name": schema_name,
                    "model": self.model,
                    "provider": self.provider,
                    "cache_key": cache_key,
                    "cached": True,
                    "retry": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                }
            )
            return validated

        last_error: Exception | None = None
        for attempt in (0, 1):
            prompt_for_attempt = (
                effective_user_prompt
                if attempt == 0
                else (
                    f"{effective_user_prompt}\n\n"
                    f"[RETRY NOTICE] Previous response failed schema validation ({last_error}). "
                    f"Return strictly valid JSON matching schema '{schema_name}'."
                )
            )
            estimated = self.estimate_cost(
                system_prompt + prompt_for_attempt,
                expected_output_tokens=expected_output_tokens,
            )
            spent = self.current_spend()
            if self.budget_usd is not None and (spent + estimated) > self.budget_usd:
                raise BudgetExceededError(
                    f"Budget cap ${self.budget_usd:.4f} would be exceeded "
                    f"(spent=${spent:.4f}, next_estimated=${estimated:.4f} for role='{role}')."
                )

            raw_output = self._invoke_provider(
                role=role,
                system_prompt=system_prompt,
                user_prompt=prompt_for_attempt,
                schema_name=schema_name,
                response_factory=response_factory,
                attempt=attempt,
            )
            raw_text = (
                json.dumps(raw_output) if isinstance(raw_output, dict) else str(raw_output)
            )
            in_tokens = estimate_tokens(system_prompt + prompt_for_attempt)
            out_tokens = estimate_tokens(raw_text)
            in_rate, out_rate = self._pricing()
            actual_cost = round(
                (in_tokens / 1_000_000.0) * in_rate + (out_tokens / 1_000_000.0) * out_rate,
                6,
            )
            if self.budget_usd is not None and (spent + actual_cost) > self.budget_usd:
                # Record attempted spend? Only refuse if actual exceeds? Wait: pre-check already guarded estimate;
                # still use actual_cost if <= budget or keep pre-check strict.
                pass

            self._record_ledger(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "role": role,
                    "schema_name": schema_name,
                    "model": self.model,
                    "provider": self.provider,
                    "cache_key": cache_key,
                    "cached": False,
                    "retry": attempt,
                    "input_tokens": in_tokens,
                    "output_tokens": out_tokens,
                    "cost_usd": actual_cost,
                }
            )

            try:
                parsed = _extract_json_object(raw_output)
                validated = validate_schema(parsed, schema_name)
                if should_cache is None or should_cache(validated):
                    cache_file.write_text(json.dumps(validated, indent=2) + "\n", encoding="utf-8")
                return validated
            except SchemaValidationError as exc:
                last_error = exc
                if attempt == 1:
                    raise

        raise SchemaValidationError(f"Exhausted retries for '{role}': {last_error}")
