import pytest

from ems_adapter.config_loader import (
    build_policy_context_view,
    compile_core_config_plan_from_grouped_config,
    load_grouped_ems_config,
)
from ems_core.net_zero.engine import _generic_surplus_candidate_contexts
from ems_core.net_zero.surplus_device_targets import build_surplus_device_targets


def _candidate(device_id, *, priority=1, threshold_w=2000, enabled=True, **overrides):
    item = {
        'device_id': device_id,
        'priority': priority,
        'threshold_w': threshold_w,
        'surplus_dispatch_mode': 'max_absorb',
        'enabled': enabled,
        'force_on': False,
        'active': False,
        'activation_allowed': True,
        'threshold_source': 'device_capabilities.max_absorb_w',
    }
    item.update(overrides)
    return item


@pytest.mark.unit
def test_generic_builder_does_not_derive_missing_activation_threshold_from_device_shape():
    targets = build_surplus_device_targets(
        (
            _candidate('EV_CHARGER', threshold_w=0),
            _candidate('HOME_BATTERY', threshold_w=0),
        )
    )

    assert [target.threshold_w for target in targets] == [0, 0]
    assert all(target.incremental_surplus_threshold_w is None for target in targets)


@pytest.mark.unit
def test_generic_builder_preserves_independent_device_thresholds_and_dispatch_modes():
    targets = build_surplus_device_targets(
        (
            _candidate('EV_A', priority=4, threshold_w=4400, surplus_dispatch_mode='max_absorb'),
            _candidate('EV_B', priority=3, threshold_w=3600, surplus_dispatch_mode='max_absorb'),
            _candidate('RELAY1', priority=2, threshold_w=2600, surplus_dispatch_mode='fixed'),
        )
    )

    assert [(target.device_id, target.threshold_w) for target in targets] == [
        ('EV_A', 4400),
        ('EV_B', 3600),
        ('RELAY1', 2600),
    ]
    assert [target.surplus_dispatch_mode for target in targets] == [
        'max_absorb',
        'max_absorb',
        'fixed',
    ]


@pytest.mark.unit
def test_generic_builder_preserves_caller_owned_eligibility_and_lifecycle_flags():
    targets = build_surplus_device_targets(
        (
            _candidate('EV_A', enabled=False, activation_allowed=False),
            _candidate('RELAY1', enabled=True, force_on=True, active=True),
        )
    )

    assert targets[0].enabled is False
    assert targets[0].activation_allowed is False
    assert targets[1].force_on is True
    assert targets[1].active is True


@pytest.mark.unit
def test_generic_builder_accepts_neutral_absorb_candidate_without_kind_contract():
    targets = build_surplus_device_targets(
        (
            _candidate(
                'THERMAL_BUFFER',
                priority=5,
                threshold_w=2000,
                surplus_dispatch_mode='max_absorb',
            ),
        )
    )

    assert len(targets) == 1
    assert targets[0].device_id == 'THERMAL_BUFFER'
    assert targets[0].priority == 5
    assert targets[0].threshold_w == 2000
    assert targets[0].surplus_dispatch_mode == 'max_absorb'


@pytest.mark.unit
def test_core_config_view_second_ev_enters_generic_candidate_context_without_materializing_ev(project_root, monkeypatch):
    grouped = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    grouped['ems']['devices']['EV_GARAGE'] = {
        'kind': 'EV_CHARGER',
        'capabilities': {
            'can_absorb_w': True,
            'can_produce_w': False,
            'supports_primary_regulation': True,
            'supports_residual_regulation': False,
            'uses_hard_off_lifecycle': True,
            'min_absorb_w': 'input_number.ems_ev_garage_min_power_w',
            'max_absorb_w': 'input_number.ems_ev_garage_max_power_w',
            'step_w': 'input_number.ems_ev_garage_power_step_w',
        },
        'policy': {
            'priority': 'input_number.ems_surplus_ev_garage_priority',
            'surplus_allowed': 'input_boolean.ems_ev_garage_surplus_allowed',
            'surplus_dispatch_mode': 'max_absorb',
            'force_on': 'input_boolean.ems_ev_garage_force_on',
            'low_pv_threshold_w': 'input_number.ems_ev_garage_low_pv_threshold_w',
            'hard_off_low_pv_cycles': 'input_number.ems_ev_garage_low_pv_cycles',
            'hard_off_release_cycles': 'input_number.ems_ev_garage_release_cycles',
        },
        'adapter': {
            'enabled': 'switch.ev_garage_enabled',
            'current_a': 'number.ev_garage_current_a',
            'current_step_a': 'input_number.ems_ev_garage_current_step_a',
            'phases': 'input_number.ems_ev_garage_phases',
            'voltage_v': 'input_number.ems_ev_garage_voltage_v',
        },
    }
    plan = compile_core_config_plan_from_grouped_config(grouped)
    values = {
        'input_number.ems_ev_garage_min_power_w': 1380,
        'input_number.ems_ev_garage_max_power_w': 3680,
        'input_number.ems_ev_garage_power_step_w': 460,
        'input_number.ems_surplus_ev_garage_priority': 4,
        'input_boolean.ems_ev_garage_surplus_allowed': True,
        'input_boolean.ems_ev_garage_force_on': False,
        'input_number.ems_ev_garage_low_pv_threshold_w': 1600,
        'input_number.ems_ev_garage_low_pv_cycles': 2,
        'input_number.ems_ev_garage_release_cycles': 2,
        'input_number.ems_ev_garage_current_step_a': 2,
        'input_number.ems_ev_garage_phases': 1,
        'input_number.ems_ev_garage_voltage_v': 230,
    }
    call_counts = {}
    real_build_ev = __import__('ems_adapter.config_loader', fromlist=['_build_view_ev_device'])._build_view_ev_device

    def counting_build_ev(plan_arg, values_arg):
        device_id = str(plan_arg.device_id)
        call_counts[device_id] = int(call_counts.get(device_id, 0) or 0) + 1
        return real_build_ev(plan_arg, values_arg)

    monkeypatch.setattr('ems_adapter.config_loader._build_view_ev_device', counting_build_ev)
    cfg = build_policy_context_view(plan, lambda entity_id, default: values.get(entity_id, default))

    contexts = _generic_surplus_candidate_contexts(
        cfg,
        active_device_ids=(),
        lifecycle_transitions_by_id={},
        primary_device_id='HOME_BATTERY',
        facts=cfg.policy_runtime_facts(),
    )
    by_id = {item['device_id']: item for item in contexts}

    assert 'EV_GARAGE' in by_id
    assert by_id['EV_GARAGE']['priority'] == 4
    assert by_id['EV_GARAGE']['threshold_w'] == 3680
    assert by_id['EV_GARAGE']['threshold_source'] == 'device_capabilities.max_absorb_w'
    assert by_id['EV_GARAGE']['surplus_dispatch_mode'] == 'max_absorb'
    assert call_counts == {}
