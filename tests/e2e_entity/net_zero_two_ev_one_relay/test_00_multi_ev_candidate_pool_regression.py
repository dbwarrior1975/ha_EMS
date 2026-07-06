import pytest

from tests.e2e_entity.net_zero_inputs import expect_derived_for_net_zero_intent
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent
from tests.e2e_entity.net_zero_two_ev_one_relay.scenario_steps import build_harness
from tests.e2e_entity.net_zero_two_ev_one_relay.scenario_steps import run_steps


@pytest.mark.scenario
def test_two_evs_and_relay_share_generic_surplus_candidate_pool(project_root):
    h = build_harness(project_root)
    E = h.ent

    run_steps(
        h,
        [
            {
                'at_s': 0,
                'note': 'Both eligible EVs and RELAY1 must be visible in one generic surplus candidate pool.',
                'set': runtime_inputs_for_net_zero_intent(
                    E,
                    rpnz_w=-10.0,
                    required_power_consumption_kw=0.0,
                    at_s=0,
                ),
                'expect_derived': expect_derived_for_net_zero_intent(
                    rpnz_w=-10.0,
                    required_power_consumption_kw=0.0,
                    at_s=0,
                ),
            }
        ],
    )

    policy_trace = h.getattrs(E['policy_diagnostics'])
    candidate_ids = {
        item['device_id']
        for item in policy_trace['surplus_device_targets']
    }

    assert candidate_ids == {'EV_CHARGER', 'EV_GARAGE', 'RELAY1'}
