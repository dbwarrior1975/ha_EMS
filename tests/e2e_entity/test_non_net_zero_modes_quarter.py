import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_cheap_grid_charge_local_quarter(project_root):
    """
    Quarter scenario for MAX_EXPORT without forecast:
    - battery target should stay at local export fallback (-4000 W)
    - EV charging policy should be 0 A
    - EV actuator should be disabled / kept off
    - relays should stay off
    """

    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)
    h.set_entities({
        ENT['goal_profile']: 'CHEAP_GRID_CHARGE',
        ENT['forecast_profile']: 'NONE',
        ENT['ev_force_current_a']: 0,
    })

    for idx in range(4):
        h.step(set_values={ENT['required_power_consumption_kw']: 0.0, ENT['rpnz_w']: 0.0}, note=f'cheap-step-{idx}')
        assert h.get(ENT['policy_battery_target_w']) == 100
        assert h.get(ENT['policy_ev_current_a']) == h.get(ENT['ev_max_current_a'])
        assert h.get(ENT['policy_relay1_command']) == 0
        assert h.get(ENT['policy_relay2_command']) == 0
        attrs = h.getattrs(ENT['policy_decision_trace'])
        assert attrs['explanation'] == 'Local cheap-charge policy'


@pytest.mark.scenario
def test_max_export_local_quarter(project_root):
    """
    Quarter scenario for MAX_EXPORT without forecast:
    - battery target should stay at local export fallback (-4000 W)
    - EV current should stay at ev_min_current_a
    - relays should stay off
    """
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)
    h.set_entities({
        ENT['goal_profile']: 'MAX_EXPORT',
        ENT['forecast_profile']: 'NONE',
        ENT['ev_force_current_a']: 0,
    })

    for idx in range(4):
        h.step(set_values={ENT['required_power_consumption_kw']: 0.0, ENT['rpnz_w']: 0.0}, note=f'export-step-{idx}')
        assert h.get(ENT['policy_battery_target_w']) == -4000
        assert h.get(ENT['policy_ev_current_a']) == 0
        assert h.get(ENT['policy_relay1_command']) == 0
        assert h.get(ENT['policy_relay2_command']) == 0
        attrs = h.getattrs(ENT['policy_decision_trace'])
        assert attrs['explanation'] == 'Local export-oriented policy'
