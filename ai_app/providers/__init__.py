"""
Provider registry for ai_app.

Usage:
    from ai_app.providers import get_provider, available_providers

    provider = get_provider('anthropic')
    result = provider.generate_summary(text)
"""

import importlib

# Lazy mapping — providers are only imported when requested.
# This prevents import errors for packages that aren't installed yet.
_REGISTRY: dict[str, str] = {
    'anthropic':   'ai_app.providers.anthropic.AnthropicProvider',
    'openai':      'ai_app.providers.openai.OpenAIProvider',
    'gemini':      'ai_app.providers.gemini.GeminiProvider',
    'perplexity':  'ai_app.providers.perplexity.PerplexityProvider',
}


def get_provider(name: str):
    """
    Return a configured AIProvider instance for the given name.

    Raises ValueError   — unknown provider name.
    Raises RuntimeError — provider's API key is not set in settings/.env.
    """
    path = _REGISTRY.get(name.strip().lower())
    if not path:
        raise ValueError(
            f'Unknown AI provider: "{name}". '
            f'Available providers: {list(_REGISTRY.keys())}'
        )
    module_path, class_name = path.rsplit('.', 1)
    cls = getattr(importlib.import_module(module_path), class_name)
    provider = cls()
    if not provider.is_available():
        raise RuntimeError(
            f'Provider "{name}" is not configured. '
            f'Add its API key to .env.local — see settings.py for the exact variable name.'
        )
    return provider


def list_providers() -> list[str]:
    """All registered provider names."""
    return list(_REGISTRY.keys())


def available_providers() -> list[str]:
    """Provider names whose API keys are present in settings."""
    result = []
    for name, path in _REGISTRY.items():
        try:
            module_path, class_name = path.rsplit('.', 1)
            cls = getattr(importlib.import_module(module_path), class_name)
            if cls().is_available():
                result.append(name)
        except Exception:
            pass
    return result
