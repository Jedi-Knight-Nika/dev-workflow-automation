from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RoleRuntimeProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning_default: Literal["PROVIDER_DEFAULT", "MINIMAL", "LOW", "MEDIUM", "HIGH", "MAX"] = (
        "PROVIDER_DEFAULT"
    )
    reasoning_min: Literal["PROVIDER_DEFAULT", "MINIMAL", "LOW", "MEDIUM", "HIGH", "MAX"] = (
        "PROVIDER_DEFAULT"
    )
    reasoning_max: Literal["PROVIDER_DEFAULT", "MINIMAL", "LOW", "MEDIUM", "HIGH", "MAX"] = "MAX"
    dynamic_reasoning_allowed: bool = True
    max_output_tokens: int | None = Field(default=None, ge=256, le=1_000_000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    context_strategy: Literal["MINIMAL", "BALANCED", "DEEP"] = "BALANCED"
    max_tool_calls: int = Field(default=40, ge=1, le=200)
    job_timeout_seconds: int = Field(default=1800, ge=60, le=43_200)
    max_job_attempts: int = Field(default=2, ge=0, le=10)
    max_model_turns: int = Field(default=3, ge=1, le=20)
    structured_output_mode: Literal["REQUIRED", "PREFERRED", "NONE"] = "REQUIRED"

    @model_validator(mode="after")
    def validate_reasoning_range(self) -> "RoleRuntimeProfileWrite":
        levels = ["PROVIDER_DEFAULT", "MINIMAL", "LOW", "MEDIUM", "HIGH", "MAX"]
        if levels.index(self.reasoning_min) > levels.index(self.reasoning_max):
            raise ValueError("Reasoning minimum cannot exceed maximum")
        if (
            not levels.index(self.reasoning_min)
            <= levels.index(self.reasoning_default)
            <= levels.index(self.reasoning_max)
        ):
            raise ValueError("Default reasoning must be inside the allowed range")
        return self


class RoleOverridePolicyWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "ALLOW"
    model: str = "ALLOW"
    reasoning_level: str = "ALLOW_WITHIN_RANGE"
    max_output_tokens: str = "ALLOW"
    temperature: str = "ALLOW_IF_SUPPORTED"
    context_strategy: str = "ALLOW"
    max_tool_calls: str = "ALLOW_WITHIN_RANGE"
    job_timeout_seconds: str = "ALLOW_WITHIN_RANGE"
    permissions: str = "REDUCE_ONLY"
    system_instructions: str = "ADDITIVE_ONLY"
    allowed_results: str = "LOCKED"

    @model_validator(mode="after")
    def validate_modes(self) -> "RoleOverridePolicyWrite":
        allowed = {
            "LOCKED",
            "ALLOW",
            "ALLOW_WITHIN_RANGE",
            "ALLOW_IF_SUPPORTED",
            "REDUCE_ONLY",
            "ADDITIVE_ONLY",
            "EXPERT_ONLY",
        }
        invalid = [value for value in self.model_dump().values() if value not in allowed]
        if invalid:
            raise ValueError(f"Invalid override mode: {invalid[0]}")
        return self
