import re
import pytest


@pytest.mark.smoke
def test_ems_policy_engine_reads_max_solar_charge(project_root):
    path = project_root / 'ems_policy_engine.py'
    assert path.exists(), f'Missing: {path}'
    src = path.read_text(encoding='utf-8')
    assert 'max_solar_charge_w' in src, 'read_config() should wire max_solar_charge_w from helper to EmsConfig'


@pytest.mark.smoke
def test_ems_actuator_writers_contains_manual_skip_logic(project_root):
    path = project_root / 'ems_actuator_writers.py'
    assert path.exists(), f'Missing: {path}'
    src = path.read_text(encoding='utf-8')
    assert 'manual_skip' in src
    assert 'MANUAL_SAFE' in src


@pytest.mark.smoke
def test_entity_map_has_required_wiring(project_root):
    path = project_root / 'modules' / 'ems_adapter' / 'entity_map.py'
    assert path.exists(), f'Missing: {path}'
    src = path.read_text(encoding='utf-8')
    assert 'REPLACE_WITH_MIN_CELL_VOLTAGE_ENTITY' not in src, 'min cell voltage entity placeholder still present'
    assert 'max_solar_charge_w' in src, 'missing max_solar_charge_w mapping'
    assert 'input_number.victron_maksimi_auringon_latausteho' in src, 'expected max solar charge helper mapping missing'


@pytest.mark.smoke
def test_engine_exposes_battery_write_enabled(project_root):
    path = project_root / 'modules' / 'ems_core' / 'net_zero' / 'engine.py'
    assert path.exists(), f'Missing: {path}'
    src = path.read_text(encoding='utf-8')
    assert 'battery_write_enabled' in src


@pytest.mark.smoke
def test_models_contains_battery_write_enabled_field(project_root):
    path = project_root / 'modules' / 'ems_core' / 'domain' / 'models.py'
    assert path.exists(), f'Missing: {path}'
    src = path.read_text(encoding='utf-8')
    assert re.search(r'battery_write_enabled\s*:\s*bool', src), 'NetZeroOutputs should define battery_write_enabled: bool'
