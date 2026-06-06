import pytest

from ems_core.domain.models import (
    ControlProfile,
    GoalProfile,
    ForecastProfile,
    GuardProfile,
    SurplusTargetConfig,
    SurplusDispatchInput,
)
from ems_core.net_zero.surplus_allocator import compute_surplus_dispatch
from ems_core.net_zero.load_projection import ev_strategy_current_a, relay_strategy_command
from tests.helpers import make_profiles, make_cfg, make_haeo


def _nz_targets(*, r1_active=False, ev_active=False, r2_active=False):
    # Priorities:
    # RELAY1 = 3
    # EV     = 2
    # RELAY2 = 1
    return (
        SurplusTargetConfig(
            name='RELAY1',
            priority=3,
            rank=1,
            threshold_kw=1.0,
            enabled=True,
            force_on=False,
            active=r1_active,
        ),
        SurplusTargetConfig(
            name='EV',
            priority=2,
            rank=2,
            threshold_kw=2.0,
            enabled=True,
            force_on=False,
            active=ev_active,
        ),
        SurplusTargetConfig(
            name='RELAY2',
            priority=1,
            rank=3,
            threshold_kw=3.0,
            enabled=True,
            force_on=False,
            active=r2_active,
        ),
    )


def _load_writer_module(project_root):
    """
    Lataa ems_actuator_writers.py testattavaksi ilman Pyscript-runtimea.
    Käytetään samoja periaatteita kuin unit-writer-semantiikkatesteissä:
    - poistetaan adapter-importit
    - injektoidaan fake get_/set_/publish-funktiot
    - palautetaan namespace + state + ENT
    """
    path = project_root / 'ems_actuator_writers.py'
    src = path.read_text(encoding='utf-8')

    filtered = []
    for line in src.splitlines():
        if line.startswith('from ems_adapter.entity_map import'):
            continue
        if line.startswith('from ems_adapter.ha_adapter import'):
            continue
        filtered.append(line)
    src = '\n'.join(filtered)

    state = {}

    def _time_trigger(*args, **kwargs):
        def deco(fn):
            return fn
        return deco

    def _state_trigger(*args, **kwargs):
        def deco(fn):
            return fn
        return deco

    def get_bool(entity_id):
        return bool(state.get(entity_id, False))

    def get_float(entity_id, default=0.0):
        return float(state.get(entity_id, default))

    def get_int(entity_id, default=0):
        return int(state.get(entity_id, default))

    def get_str(entity_id, default=''):
        return str(state.get(entity_id, default))

    def set_boolean(entity_id, on):
        state[entity_id] = bool(on)

    def set_number(entity_id, value):
        state[entity_id] = value

    def publish_sensor(entity_id, value, attrs=None):
        state[entity_id] = {'value': value, 'attrs': attrs or {}}

    ENT = {
        'policy_battery_target_w': 'sensor.policy_battery',
        'actuator_victron_setpoint_w': 'input_number.test_actuator_victron_setpoint_w',
        'policy_ev_current_a': 'sensor.policy_ev',
        'actuator_ev_enabled': 'input_boolean.actuator_ev_enabled',
        'actuator_ev_current_a': 'input_number.test_actuator_ev_current_a',
        'policy_relay1_command': 'sensor.policy_relay1',
        'policy_relay2_command': 'sensor.policy_relay2',
        'actuator_relay1': 'input_boolean.actuator_relay1',
        'actuator_relay2': 'input_boolean.actuator_relay2',
    }

    ns = {
        '__name__': 'writer_test_module',
        '__file__': str(path),
        'time_trigger': _time_trigger,
        'state_trigger': _state_trigger,
        'get_bool': get_bool,
        'get_float': get_float,
        'get_int': get_int,
        'get_str': get_str,
        'set_boolean': set_boolean,
        'set_number': set_number,
        'publish_sensor': publish_sensor,
        'ENT': ENT,
    }

    code = compile(src, str(path), 'exec')
    exec(code, ns)
    return ns, state, ENT


@pytest.mark.scenario
def test_net_zero_loads_activate_and_release_in_correct_order_with_ev_min_restore(project_root):
    """
    End-to-end scenario for NET_ZERO load sequencing:

    Activation order:
        RELAY1 (priority 3) -> EV (priority 2) -> RELAY2 (priority 1)

    Release order when surplus collapses / RPNZ <= 0:
        RELAY2 -> EV -> RELAY1

    EV release semantics:
        EV policy should return 0 in NET_ZERO when burn is no longer active,
        and writer should interpret 0 as restore-to-min-current.
    """

    profiles = make_profiles(
        control=ControlProfile.AUTOMATIC,
        goal=GoalProfile.NET_ZERO,
        forecast=ForecastProfile.NONE,
        guard=GuardProfile.NORMAL_LIMITS,
    )

    cfg = make_cfg(
        ev_min_current_a=4,
        ev_max_current_a=28,
        ev_force_current_a=0,
        ev_priority=2,
        relay1_priority=3,
        relay2_priority=1,
    )

    haeo = make_haeo(
        effective_forecast=ForecastProfile.NONE,
        configured_forecast=ForecastProfile.NONE,
        fresh=True,
    )

    now = 1000.0

    # ------------------------------------------------------------------
    # PHASE 1: Activation within the same quarter
    # ------------------------------------------------------------------

    # Step 1: first activation -> RELAY1
    inp0 = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=5.0,
        rpnz_w=500.0,
        targets=_nz_targets(),
    )
    dec0 = compute_surplus_dispatch(inp0, now_ts=now, freeze_s=30)
    assert dec0.activate == 'RELAY1'

    relay1_cmd = relay_strategy_command(
        profiles=profiles,
        enabled_import_zero=True,
        force_on=False,
        net_zero_active=True,
    )
    assert relay1_cmd == 1

    # Step 2: after freeze expires and RELAY1 is active -> EV
    inp1 = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=now,
        rpc_kw=5.0,
        rpnz_w=500.0,
        targets=_nz_targets(r1_active=True),
    )
    dec1 = compute_surplus_dispatch(inp1, now_ts=now + 31, freeze_s=30)
    assert dec1.activate == 'EV'

    # EV command when burn is active in NET_ZERO -> max current
    ev_cmd_on = ev_strategy_current_a(
        profiles=profiles,
        cfg=cfg,
        haeo=haeo,
        burn_active=True,
    )
    assert ev_cmd_on == cfg.ev_max_current_a

    # Step 3: after freeze expires and RELAY1 + EV are active -> RELAY2
    inp2 = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=now,
        rpc_kw=5.0,
        rpnz_w=500.0,
        targets=_nz_targets(r1_active=True, ev_active=True),
    )
    dec2 = compute_surplus_dispatch(inp2, now_ts=now + 62, freeze_s=30)
    assert dec2.activate == 'RELAY2'

    relay2_cmd = relay_strategy_command(
        profiles=profiles,
        enabled_import_zero=True,
        force_on=False,
        net_zero_active=True,
    )
    assert relay2_cmd == 1

    # ------------------------------------------------------------------
    # PHASE 2: Surplus collapses in the same quarter -> release order
    # ------------------------------------------------------------------

    # All active, no more positive RPNZ -> release lowest priority first = RELAY2
    inp3 = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=0.0,
        rpnz_w=0.0,
        targets=_nz_targets(r1_active=True, ev_active=True, r2_active=True),
    )
    dec3 = compute_surplus_dispatch(inp3, now_ts=now + 100, freeze_s=30)
    assert dec3.release == 'RELAY2'

    # Relay2 command after release should be OFF
    relay2_cmd_off = relay_strategy_command(
        profiles=profiles,
        enabled_import_zero=True,
        force_on=False,
        net_zero_active=False,
    )
    assert relay2_cmd_off == 0

    # After RELAY2 released, next one should be EV
    inp4 = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=0.0,
        rpnz_w=0.0,
        targets=_nz_targets(r1_active=True, ev_active=True, r2_active=False),
    )
    dec4 = compute_surplus_dispatch(inp4, now_ts=now + 101, freeze_s=30)
    assert dec4.release == 'EV'

    # EV release semantics in NET_ZERO:
    # burn_active=False -> EV strategy returns 0
    ev_cmd_off = ev_strategy_current_a(
        profiles=profiles,
        cfg=cfg,
        haeo=haeo,
        burn_active=False,
    )
    assert ev_cmd_off == 0

    # Writer must interpret strategy 0 as restore-to-min-current
    writer_mod, writer_state, ENT = _load_writer_module(project_root)

    writer_state[ENT['actuator_ev_enabled']] = True
    writer_state[ENT['actuator_ev_current_a']] = 16
    writer_state[ENT['policy_ev_current_a']] = ev_cmd_off
    writer_state['input_number.ems_ev_min_current_a'] = cfg.ev_min_current_a

    ev_result = writer_mod['_write_ev_actuator']()

    assert ev_result['written'] is True
    assert ev_result['reason'] == 'restore_min_current'
    assert ev_result['target_current_a'] == cfg.ev_min_current_a
    assert writer_state[ENT['actuator_ev_current_a']] == cfg.ev_min_current_a

    # After EV released, last one should be RELAY1
    inp5 = SurplusDispatchInput(
        policy_active=True,
        freeze_until_ts=None,
        rpc_kw=0.0,
        rpnz_w=0.0,
        targets=_nz_targets(r1_active=True, ev_active=False, r2_active=False),
    )
    dec5 = compute_surplus_dispatch(inp5, now_ts=now + 102, freeze_s=30)
    assert dec5.release == 'RELAY1'

    relay1_cmd_off = relay_strategy_command(
        profiles=profiles,
        enabled_import_zero=True,
        force_on=False,
        net_zero_active=False,
    )
    assert relay1_cmd_off == 0
