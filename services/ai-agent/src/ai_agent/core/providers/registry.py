"""Provider registry - known provider presets and settings-driven factory.

A preset maps a provider key to its default OpenAI-compatible base URL.
Providers without a public API (omniroute, agentrouter, generic) have no
preset: they REQUIRE an explicit ``AI_BASE_URL``/``AI_FALLBACK_BASE_URL``.

``local_only`` clearance is operator-supplied per provider (AI_*_LOCAL_ONLY):
it asserts the endpoint runs on infrastructure the tenant controls, letting
the router route local-only (cost/sell price) prompts to it. Cloud presets
default to cleared=False - flipping them is a deliberate, auditable config
act, never an accident of defaults.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_agent.core.exceptions import StartupError
from ai_agent.core.providers.openai_compatible import OpenAiCompatibleProvider

if TYPE_CHECKING:
    from ai_agent.core.config import Settings
    from ai_agent.core.providers.base import LlmProvider

# Keys with a known default base URL. Anything else requires explicit config.
PROVIDER_PRESETS: dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
}

# Recognized-but-presetless keys (documented aliases for private gateways).
BASE_URL_REQUIRED_KEYS = frozenset({"omniroute", "agentrouter", "generic"})


def resolve_base_url(provider_key: str, override: str) -> str:
    """Return the effective base URL for a provider key.

    Raises:
        StartupError: If the key is unknown or lacks both preset and override.
    """
    override_clean = override.strip()
    if override_clean:
        return override_clean
    preset = PROVIDER_PRESETS.get(provider_key)
    if preset:
        return preset
    raise StartupError(
        f"AI provider '{provider_key}' has no known base URL preset - set AI_BASE_URL explicitly"
    )


def build_provider(
    *,
    provider_key: str,
    model: str,
    base_url_override: str = "",
    api_key: str = "",
    local_only: bool = False,
    native: bool = False,
    timeout_seconds: float,
) -> LlmProvider:
    """Instantiate one provider from its configuration quartet.

    Raises:
        StartupError: On an unknown provider key or unresolvable base URL.
    """
    _validate_key(provider_key)
    return OpenAiCompatibleProvider(
        name=provider_key,
        model=model.strip(),
        base_url=resolve_base_url(provider_key, base_url_override),
        api_key=api_key,
        local_only=local_only,
        native=native,
        timeout_seconds=timeout_seconds,
    )


def build_providers_from_settings(config: Settings) -> list[LlmProvider]:
    """Build [primary?, fallback?] from settings; empty when none configured.

    Called ONCE at startup; unknown keys fail fast here so a typo'd
    ``AI_PROVIDER`` never survives boot.
    """
    providers: list[LlmProvider] = []
    if config.PROVIDER is not None:
        providers.append(
            build_provider(
                provider_key=config.PROVIDER,
                model=config.MODEL,
                base_url_override=config.BASE_URL,
                api_key=config.API_KEY,
                local_only=config.PROVIDER_LOCAL_ONLY,
                native=config.PROVIDER_NATIVE,
                timeout_seconds=config.PROVIDER_TIMEOUT_SECONDS,
            )
        )
    if config.FALLBACK_PROVIDER is not None:
        providers.append(
            build_provider(
                provider_key=config.FALLBACK_PROVIDER,
                model=config.FALLBACK_MODEL,
                base_url_override=config.FALLBACK_BASE_URL,
                api_key=config.FALLBACK_API_KEY,
                local_only=config.FALLBACK_LOCAL_ONLY,
                timeout_seconds=config.PROVIDER_TIMEOUT_SECONDS,
            )
        )
    return providers


def _validate_key(provider_key: str) -> None:
    known = set(PROVIDER_PRESETS) | BASE_URL_REQUIRED_KEYS
    if provider_key not in known:
        raise StartupError(
            f"Unknown AI provider '{provider_key}' - expected one of {sorted(known)}"
        )
