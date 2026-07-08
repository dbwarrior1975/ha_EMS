from pathlib import Path

from ems_adapter.config_loader import load_grouped_ems_config
from ems_adapter.runtime_context import build_runtime_entities_from_grouped_config


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_entities():
    # Legacy dynamic-ref contract tests need the full entity registry even when
    # the production EMS_config.yaml uses the runtime packet schema.
    config = load_grouped_ems_config(_project_root() / 'example_EMS_config.yaml')
    return build_runtime_entities_from_grouped_config(config)


ENT = _load_entities()
