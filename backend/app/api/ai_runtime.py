from fastapi import APIRouter

from app.providers.capabilities import ModelCapabilityRegistry

router = APIRouter(prefix="/ai", tags=["ai-runtime"])


@router.get("/providers/{provider}/models/{model:path}/capabilities")
async def model_capabilities(provider: str, model: str) -> dict[str, object]:
    capabilities = ModelCapabilityRegistry().get(provider, model)
    return {
        "provider": capabilities.provider,
        "model": capabilities.model,
        "context_window": None,
        "max_output_tokens": capabilities.max_output_tokens,
        "reasoning_supported": len(capabilities.reasoning_levels) > 1,
        "reasoning_levels": [item.value for item in capabilities.reasoning_levels],
        "temperature_supported": capabilities.temperature_supported,
        "structured_output_supported": capabilities.structured_output_supported,
        "tools_supported": capabilities.tools_supported,
        "parallel_tool_calls_supported": capabilities.parallel_tool_calls_supported,
        "capability_version": capabilities.version,
    }
