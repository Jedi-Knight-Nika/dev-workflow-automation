from app.providers.base import AIProvider
from app.providers.http import AnthropicProvider, GoogleProvider, OpenAIProvider


def create_provider(name: str, api_key: str) -> AIProvider:
    providers: dict[str, type[AIProvider]] = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "google": GoogleProvider,
    }
    try:
        return providers[name](api_key)
    except KeyError as exc:
        raise ValueError(f"Unsupported AI provider: {name}") from exc
