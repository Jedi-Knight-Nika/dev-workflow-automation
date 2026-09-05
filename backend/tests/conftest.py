import os

# Unit tests must never start the database-backed scheduler as an import side effect.
os.environ["SCHEDULER_ENABLED"] = "false"
