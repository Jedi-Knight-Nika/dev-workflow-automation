from app.agent_runtime.infrastructure.catalog_base import AIProvider
from app.agent_runtime.infrastructure.catalog_http import (
    AnthropicProvider,
    DeepSeekProvider,
    OpenAIProvider,
)


def create_provider(name: str, api_key: str) -> AIProvider:
    providers: dict[str, type[AIProvider]] = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "deepseek": DeepSeekProvider,
    }
    try:
        return providers[name](api_key)
    except KeyError as exc:
        raise ValueError(f"Unsupported AI provider: {name}") from exc
