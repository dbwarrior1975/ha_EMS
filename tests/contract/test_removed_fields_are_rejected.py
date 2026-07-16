import pytest

from ems_adapter.config_loader import (
    SEVERITY_ERROR,
    load_grouped_ems_config,
    validate_grouped_ems_config,
)
from ems_adapter.direct_runtime import (
    RuntimePacketSchemaError,
    parse_policy_config_cached,
    reset_direct_runtime_cache,
)
from tests.unit.test_direct_runtime import _policy_packet, _topology


def _error_paths(result):
    return {issue.path for issue in result.issues if issue.severity == SEVERITY_ERROR}


def _error_messages(result):
    return {issue.path: issue.message for issue in result.issues if issue.severity == SEVERITY_ERROR}


@pytest.mark.contract
@pytest.mark.parametrize('value', (0, -1, -0.5, 4400))
def test_grouped_config_rejects_removed_device_activation_threshold_field(project_root, value):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    config['ems']['devices']['EV_CHARGER']['policy']['activation_threshold_w'] = value

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert 'ems.devices.EV_CHARGER.policy.activation_threshold_w' in _error_paths(result)


@pytest.mark.contract
def test_grouped_config_rejects_removed_runtime_derived_input_fields(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    runtime = config['ems']['runtime']
    runtime['required_power_w'] = 'sensor.required_power_consumption'
    runtime['rpnz_w'] = 'sensor.ems_calculated_required_power_for_net_zero'
    runtime['pv_power_kw'] = 'sensor.pv_kw'

    result = validate_grouped_ems_config(config)

    messages = _error_messages(result)
    assert messages['ems.runtime.required_power_w'] == (
        'runtime.required_power_w is no longer accepted; required power is derived inside EMS '
        'from grid_power_w, quarter_energy_balance_kwh, and current quarter time.'
    )
    assert messages['ems.runtime.rpnz_w'] == (
        'runtime.rpnz_w is no longer accepted; RPNZ is derived inside EMS from '
        'quarter_energy_balance_kwh and current quarter time.'
    )
    assert messages['ems.runtime.pv_power_kw'] == (
        'runtime.pv_power_kw is no longer accepted; use runtime.pv_power_w.'
    )


@pytest.mark.contract
def test_grouped_config_rejects_removed_adjustable_surplus_alias(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    config['ems']['global_config']['adjustable_surplus_load'] = 'RELAY1'

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert 'ems.global_config.adjustable_surplus_load' in _error_paths(result)


@pytest.mark.contract
@pytest.mark.parametrize(
    ('field', 'value'),
    (
        ('adjustable_surplus_load', 'EV_CHARGER'),
        ('adjustable_surplus_activation_w', 2300),
    ),
)
def test_direct_runtime_v5_rejects_removed_surplus_config_fields(project_root, field, value):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=180)
    packet['config'][field] = value

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == f'policy_config.config.{field}'
    assert 'field removed' in str(exc.value)


@pytest.mark.contract
def test_direct_runtime_v5_rejects_removed_adjustable_surplus_alias(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=18)
    packet['config']['adjustable_surplus_load'] = 'RELAY1'

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.config.adjustable_surplus_load'


@pytest.mark.contract
def test_direct_runtime_v5_rejects_removed_adjustable_primary_alias(project_root):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=1891)
    packet['config'].pop('primary_consuming_device_ids')
    packet['config']['adjustable_primary_load'] = 'HOME_BATTERY'

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.config.primary_consuming_device_ids'


@pytest.mark.contract
@pytest.mark.parametrize('value', (0, -1, 4400))
def test_direct_runtime_v5_rejects_removed_device_activation_threshold_field(project_root, value):
    reset_direct_runtime_cache()
    topology = _topology(project_root)
    packet = _policy_packet(revision=194)
    packet['devices']['EV_CHARGER']['policy']['activation_threshold_w'] = value

    with pytest.raises(RuntimePacketSchemaError) as exc:
        parse_policy_config_cached(topology, packet)

    assert exc.value.path == 'policy_config.devices.EV_CHARGER.policy.activation_threshold_w'
    assert 'field removed' in str(exc.value)
