from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeliveryRetryPolicy:
    max_attempts: int = 5
    max_error_chars: int = 2_000

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.max_error_chars < 1:
            raise ValueError("max_error_chars must be positive")

    def exhausted(self, attempts: int) -> bool:
        return attempts >= self.max_attempts

    def error_message(self, error: Exception) -> str:
        return str(error)[: self.max_error_chars]
