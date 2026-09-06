from app.domain.ai_runtime import ModelCapabilities, ReasoningLevel


class ModelCapabilityRegistry:
    """Conservative static registry; unknown models receive provider defaults only."""

    version = "2026-09-06"

    def get(self, provider: str, model: str) -> ModelCapabilities:
        provider_name = provider.casefold()
        model_name = model.casefold()
        reasoning: tuple[ReasoningLevel, ...] = (ReasoningLevel.PROVIDER_DEFAULT,)
        temperature = True
        openai_reasoning = provider_name == "openai" and model_name.startswith(
            ("gpt-5", "o1", "o3", "o4")
        )
        modern_anthropic = provider_name == "anthropic" and any(
            marker in model_name for marker in ("4-6", "4.6", "4-7", "4.7", "4-8", "5")
        )
        if openai_reasoning or modern_anthropic:
            reasoning = (
                ReasoningLevel.PROVIDER_DEFAULT,
                ReasoningLevel.LOW,
                ReasoningLevel.MEDIUM,
                ReasoningLevel.HIGH,
            )
            temperature = False
        elif provider_name == "google" and model_name.startswith("gemini-3"):
            if model_name.startswith("gemini-3-pro"):
                reasoning = (
                    ReasoningLevel.PROVIDER_DEFAULT,
                    ReasoningLevel.LOW,
                    ReasoningLevel.HIGH,
                )
            elif "flash-lite-image" in model_name:
                reasoning = (ReasoningLevel.PROVIDER_DEFAULT, ReasoningLevel.HIGH)
            elif model_name.startswith(("gemini-3.8", "gemini-3.7", "gemini-3.1-pro")):
                reasoning = (
                    ReasoningLevel.PROVIDER_DEFAULT,
                    ReasoningLevel.LOW,
                    ReasoningLevel.MEDIUM,
                    ReasoningLevel.HIGH,
                )
            else:
                reasoning = (
                    ReasoningLevel.PROVIDER_DEFAULT,
                    ReasoningLevel.MINIMAL,
                    ReasoningLevel.LOW,
                    ReasoningLevel.MEDIUM,
                    ReasoningLevel.HIGH,
                )
            temperature = False
        return ModelCapabilities(
            provider,
            model,
            reasoning,
            max_output_tokens=None,
            temperature_supported=temperature,
            structured_output_supported=provider_name in {"openai", "anthropic", "google"},
            tools_supported=provider_name in {"openai", "anthropic", "google"},
            parallel_tool_calls_supported=provider_name == "openai",
            version=self.version,
        )
