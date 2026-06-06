import pytest

from ems_adapter.entity_map import ENT
from tests.e2e_entity.scenario_harness import QuarterScenarioHarness


@pytest.mark.scenario
def test_battery_protect_min_cell_trigger_and_recovery_quarter(project_root):
    """
    Quarter story:
    - quarter starts in NORMAL_LIMITS
    - SOC and min cell voltage drops below threshold -> BATTERY_PROTECT    
    - later only SOC recovery over  margin
    - later both SOC recovery margin and min cell threshold are satisfied    
    - min cell voltage drops below threshold -> BATTERY_PROTECT
    - later both SOC recovery margin and min cell threshold are satisfied
      while guard_profile is BATTERY_PROTECT -> NORMAL_LIMITS recovery path is exercised
    """
    h = QuarterScenarioHarness(project_root=project_root, start_ts=0.0, step_s=30)

    steps = [
        {
            'note': 't0 normal baseline',
            'set': {
                ENT['guard_profile']: 'NORMAL_LIMITS',
                ENT['soc']: 10.0,
                ENT['min_cell_voltage_v']: 3.2,
                ENT['battery_protect_soc']: 1.0,
                ENT['battery_protect_soc_recovery_margin']: 1.0,
                ENT['battery_protect_min_cell_voltage_v']: 3.05,
            },
            'expect_policy_values': {
                ENT['policy_decision_trace']: 'AUTOMATIC/NET_ZERO/NORMAL_LIMITS/NONE',
            },
        },
        {
            'note': 't30 min soc drops below threshold -> battery protect',
            'set': {
                ENT['soc']: 0.0,
                ENT['min_cell_voltage_v']: 3.04,
            },
            'expect_policy': {
                'guard': 'BATTERY_PROTECT',
                'guard_reason': 'Battery protect active: SOC and minimum cell voltage below thresholds',
                'dominant_limitation': 'BATTERY_SOC_LIMIT',
            },
        },
        {
            'note': 't60 only half recovery values restored and input guard set to BATTERY_PROTECT to exercise explicit recovery path',
            'set': {
                ENT['guard_profile']: 'BATTERY_PROTECT',
                ENT['soc']: 1.0,
                ENT['min_cell_voltage_v']: 3.055,
            },
            'expect_policy': {
                'guard': 'BATTERY_PROTECT',
                'guard_reason': 'Battery protect persists until SOC recovery margin and minimum cell voltage threshold are both satisfied',
            },
        },        
        {
            'note': 't90 all recovery values restored and input guard set to BATTERY_PROTECT to exercise explicit recovery path',
            'set': {
                ENT['guard_profile']: 'BATTERY_PROTECT',
                ENT['soc']: 2.0,
                ENT['min_cell_voltage_v']: 3.055,
            },
            'expect_policy': {
                'guard': 'NORMAL_LIMITS',
                'guard_reason': 'Guard recovered: SOC recovery margin reached and minimum cell voltage threshold restored',
            },
        },
        {
            'note': 't120 min cell voltage drops below threshold -> battery protect',
            'set': {
                ENT['soc']: 1.0,
                ENT['min_cell_voltage_v']: 3.045,
            },
            'expect_policy': {
                'guard': 'BATTERY_PROTECT',
                'guard_reason': 'Battery protect active: minimum cell voltage below threshold',
                'dominant_limitation': 'BATTERY_SOC_LIMIT',
            },
        },        
        {
            'note': 't150 recovery values restored and input guard set to BATTERY_PROTECT to exercise explicit recovery path',
            'set': {
                ENT['guard_profile']: 'BATTERY_PROTECT',
                ENT['soc']: 2.0,
                ENT['min_cell_voltage_v']: 3.06,
            },
            'expect_policy': {
                'guard': 'NORMAL_LIMITS',
                'guard_reason': 'Guard recovered: SOC recovery margin reached and minimum cell voltage threshold restored',
            },
        },
    ]

    for idx, step in enumerate(steps):
        h.step(set_values=step.get('set', {}), note=step['note'])

        policy_trace = h.getattrs(ENT['policy_decision_trace'])

        for attr, expected in step.get('expect_policy', {}).items():
            actual = policy_trace.get(attr)
            assert actual == expected, (
                f"step={idx} note={step['note']} policy.{attr} actual={actual} expected={expected}"
            )

        for entity_id, expected in step.get('expect_policy_values', {}).items():
            actual = h.get(entity_id)
            assert actual == expected, (
                f"step={idx} note={step['note']} policy_value entity={entity_id} "
                f"actual={actual} expected={expected}"
            )
