from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidationEvidence:
    repository_sha: str
    configuration_hash: str
    status: str


def evidence_is_current(
    evidence: ValidationEvidence, *, repository_sha: str, configuration_hash: str
) -> bool:
    return (
        evidence.status == "PASSED"
        and evidence.repository_sha == repository_sha
        and evidence.configuration_hash == configuration_hash
    )
