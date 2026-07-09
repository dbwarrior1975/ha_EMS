from pathlib import Path

from ems_adapter.config_loader import load_grouped_ems_config
from tests.e2e_entity.entity_registry import build_scenario_entity_registry


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_entities():
    config = load_grouped_ems_config(_project_root() / "example_EMS_config.yaml")
    return build_scenario_entity_registry(config)


ENT = _load_entities()
