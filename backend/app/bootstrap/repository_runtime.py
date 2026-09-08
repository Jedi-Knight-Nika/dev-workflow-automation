from app.bootstrap.observability import supporting_sessions
from app.platform.configuration.settings import get_settings
from app.repositories.application.runtime_profiles import RepositoryRuntimes
from app.repositories.infrastructure.runtime_profiles import SqlRepositoryRuntimes


def repository_runtimes() -> RepositoryRuntimes:
    return SqlRepositoryRuntimes(supporting_sessions(), get_settings().developer_container_image)
