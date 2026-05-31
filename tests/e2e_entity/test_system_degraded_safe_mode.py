import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_soc_stale_enters_safe_mode(project_root):
    """Stale Victron heartbeat pushes guard into DEGRADED and clamps policy outputs."""
    h = QuarterScenarioHarness(project_root=project_root, start_ts=1000.0, step_s=30)
    h.set_entities({
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['soc']: 50.0,
        ENT['victron_heartbeat']: 0.0,
    })
    h.set_stale(ENT['victron_heartbeat'], 1000.0)

    h.step(set_values={ENT['required_power_consumption_kw']: 4.0, ENT['rpnz_w']: 500}, note='stale victron enters degraded')
    attrs = h.getattrs(ENT['policy_decision_trace'])
    assert attrs['guard'] == 'DEGRADED'
    assert attrs['dominant_limitation'] == 'SYSTEM_DEGRADED'
    assert h.get(ENT['policy_battery_target_w']) == 0
    assert h.get(ENT['policy_ev_current_a']) == -1


@pytest.mark.scenario
def test_writer_freeze_in_system_degraded(project_root):
    """In DEGRADED the latch state clears, but writers skip existing EV/relay actuators."""
    h = QuarterScenarioHarness(project_root=project_root, start_ts=1000.0, step_s=30)
    h.set_entities({
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['soc']: 50.0,
        ENT['victron_heartbeat']: 0.0,
        ENT['surplus_ev_active']: True,
        ENT['surplus_r1_active']: True,
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 16,
        ENT['actuator_relay1']: True,
    })
    h.set_stale(ENT['victron_heartbeat'], 1000.0)

    h.step(set_values={ENT['required_power_consumption_kw']: 4.0, ENT['rpnz_w']: 500}, note='degraded clears latches and skips ev')
    assert h.get(ENT['surplus_ev_active']) is False
    assert h.get(ENT['surplus_r1_active']) is False
    assert h.get(ENT['actuator_relay1']) is True
    assert h.get(ENT['actuator_ev_enabled']) is True
    assert h.get(ENT['actuator_ev_current_a']) == 16
    attrs = h.getattrs('sensor.ems_actuator_writer_trace')
    assert attrs['ev']['reason'] == 'policy_skip'
    assert attrs['relay1']['reason'] == 'policy_skip'
