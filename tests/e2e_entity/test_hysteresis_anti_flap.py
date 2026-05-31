import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_relay_no_chatter_near_threshold(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)
    h.set_entities({ENT['goal_profile']: 'NET_ZERO', ENT['forecast_profile']: 'NONE'})

    h.step(set_values={ENT['required_power_consumption_kw']: 2.6, ENT['rpnz_w']: 500}, note='activate relay1')
    assert h.get(ENT['surplus_r1_active']) is True

    # Freeze keeps allocator from immediately activating next target despite still-high RPC.
    h.step(set_values={ENT['required_power_consumption_kw']: 2.7, ENT['rpnz_w']: 500}, note='freeze holds')
    assert h.get(ENT['surplus_r1_active']) is True
    assert h.get(ENT['surplus_ev_active']) is False
    attrs = h.getattrs('sensor.ems_surplus_latch_trace')
    assert attrs['decision'] == 'NOOP'


@pytest.mark.scenario
def test_ev_current_no_oscillation(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)
    h.set_entities({
        ENT['goal_profile']: 'NET_ZERO',
        ENT['forecast_profile']: 'NONE',
        ENT['actuator_ev_enabled']: True,
        ENT['actuator_ev_current_a']: 16,
    })

    # First step releases EV burn to min current.
    h.step(set_values={ENT['required_power_consumption_kw']: 0.0, ENT['rpnz_w']: 500, ENT['surplus_ev_active']: False}, note='release to min')
    assert h.get(ENT['actuator_ev_current_a']) == 4

    # Next identical step should remain stable without further oscillation.
    h.step(set_values={ENT['required_power_consumption_kw']: 0.0, ENT['rpnz_w']: 500}, note='stable min')
    assert h.get(ENT['actuator_ev_current_a']) == 4
    attrs = h.getattrs('sensor.ems_actuator_writer_trace')
    assert attrs['ev']['reason'] in ('already_released', 'restore_min_current')


@pytest.mark.scenario
def test_rpc_noise_stability(project_root):
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)
    h.set_entities({ENT['goal_profile']: 'NET_ZERO', ENT['forecast_profile']: 'NONE'})

    # Noise below first threshold should not activate any surplus target.
    for idx, rpc_kw in enumerate((0.2, 0.6, 0.9, 0.8)):
        h.step(set_values={ENT['required_power_consumption_kw']: rpc_kw, ENT['rpnz_w']: 500}, note=f'noise-{idx}')
        assert h.get(ENT['surplus_r1_active']) is False
        assert h.get(ENT['surplus_ev_active']) is False
        assert h.get(ENT['surplus_r2_active']) is False
