import pytest

from tests.e2e_entity.net_zero_ev_adjustable_load.scenario_steps import build_harness
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent


@pytest.mark.scenario
def test_primary_absorber_residual_producer_feedback_protection_progresses_lifecycle(project_root):
    """A real primary->residual production loop is blocked by topology, not EV kind."""
    h = build_harness(project_root)
    E = h.ent

    for at_s, expected_low_cycles, expected_hard_off in (
        (0, 1, False),
        (30, 2, True),
    ):
        h.step(
            at_s=at_s,
            note='primary absorber with a different producing residual regulator',
            set_values={
                **runtime_inputs_for_net_zero_intent(
                    E,
                    rpnz_w=500.0,
                    required_power_consumption_kw=3.0,
                    at_s=at_s,
                    pv_power_kw=0.0,
                ),
                E['current_battery_sp']: -1200.0,
                E['devices']['EV_CHARGER']['force_on']: False,
            },
        )

        policy_trace = h.getattrs(E['policy_diagnostics'])
        policies = {
            item['device_id']: item
            for item in policy_trace['device_policies']
        }
        ev_lifecycle = policy_trace['device_lifecycle_states']['EV_CHARGER']

        assert policy_trace['feedback_protection_active'] is True
        assert policy_trace['feedback_protection_primary_consuming_device_id'] == 'EV_CHARGER'
        assert policy_trace['feedback_protection_producing_device_id'] == 'HOME_BATTERY'
        assert policy_trace['feedback_protection_producer_active'] is True
        assert policy_trace['activation_block_reason'] == 'primary_producer_feedback_protection'
        assert 'battery_to_ev_loop_risk' not in policy_trace
        assert ev_lifecycle['low_pv_cycles'] == expected_low_cycles
        assert ev_lifecycle['hard_off_active'] is expected_hard_off

        writer_ev = h.getattrs(E['actuator_writer_trace'])['devices']['EV_CHARGER']
        if expected_hard_off:
            assert policies['EV_CHARGER']['target_w'] == 0
            assert policies['EV_CHARGER']['enabled'] is False
            assert policies['EV_CHARGER']['mode'] == 'hard_off'
            assert writer_ev['action'] == 'hard_off'
            assert h.get(E['actuator_ev_enabled']) is False
        else:
            # Feedback protection makes the EV unrealizable for this tick.
            # The canonical resolver skips it instead of restoring a positive
            # minimum that would reinforce the battery-to-EV control loop.
            assert policies['EV_CHARGER']['target_w'] == 0
            assert policies['EV_CHARGER']['enabled'] is False
            assert policies['EV_CHARGER']['mode'] == 'restore_min'
            assert policies['EV_CHARGER']['reason'] == 'ev_policy_inactive'
            assert policy_trace['primary_consuming_skipped_by_id']['EV_CHARGER'] == 'producer_feedback_protection'
            assert writer_ev['action'] == 'restore_min_current'
            assert h.get(E['actuator_ev_enabled']) is False
