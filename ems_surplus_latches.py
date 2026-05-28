from datetime import datetime

from ems_adapter.entity_map import ENT
from ems_adapter.ha_adapter import get_attr, get_bool, get_str, set_boolean, publish_sensor, parse_input_datetime_ts


def _set_freeze_until_ts(entity_id, ts):
    if ts in (None, '', 'unknown', 'unavailable'):
        return False

    try:
        target_ts = float(ts)
    except Exception:
        return False

    current_ts = parse_input_datetime_ts(entity_id)
    if current_ts is not None and abs(current_ts - target_ts) < 1.0:
        return False

    dt = datetime.fromtimestamp(target_ts)
    input_datetime.set_datetime(
        entity_id=entity_id,
        date=dt.strftime('%Y-%m-%d'),
        time=dt.strftime('%H:%M:%S'),
    )
    return True


def _apply_dispatch(decision):
    written = []

    if decision == 'ACTIVATE_RELAY1':
        if not get_bool(ENT['surplus_r1_active']):
            set_boolean(ENT['surplus_r1_active'], True)
            written.append('relay1_on')

    elif decision == 'ACTIVATE_EV':
        if not get_bool(ENT['surplus_ev_active']):
            set_boolean(ENT['surplus_ev_active'], True)
            written.append('ev_on')

    elif decision == 'ACTIVATE_RELAY2':
        if not get_bool(ENT['surplus_r2_active']):
            set_boolean(ENT['surplus_r2_active'], True)
            written.append('relay2_on')

    elif decision == 'RELEASE_RELAY1':
        if get_bool(ENT['surplus_r1_active']):
            set_boolean(ENT['surplus_r1_active'], False)
            written.append('relay1_off')

    elif decision == 'RELEASE_EV':
        if get_bool(ENT['surplus_ev_active']):
            set_boolean(ENT['surplus_ev_active'], False)
            written.append('ev_off')

    elif decision == 'RELEASE_RELAY2':
        if get_bool(ENT['surplus_r2_active']):
            set_boolean(ENT['surplus_r2_active'], False)
            written.append('relay2_off')

    elif decision == 'CLEAR_ALL':
        if get_bool(ENT['surplus_r1_active']):
            set_boolean(ENT['surplus_r1_active'], False)
            written.append('relay1_off')
        if get_bool(ENT['surplus_ev_active']):
            set_boolean(ENT['surplus_ev_active'], False)
            written.append('ev_off')
        if get_bool(ENT['surplus_r2_active']):
            set_boolean(ENT['surplus_r2_active'], False)
            written.append('relay2_off')

    return written


@time_trigger('period(now, 30s)')
@state_trigger('sensor.ems_net_zero_surplus_dispatch_decision_pyscript or sensor.ems_policy_decision_trace_pyscript')
def ems_surplus_latches_loop():
    decision = get_str(ENT['surplus_dispatch_decision_pys'], 'NOOP')
    freeze_until_ts = get_attr(ENT['policy_decision_trace'], 'surplus_freeze_until_ts', None)

    writes = _apply_dispatch(decision)
    freeze_written = _set_freeze_until_ts(ENT['surplus_freeze_until'], freeze_until_ts)

    publish_sensor('sensor.ems_surplus_latch_trace', decision, {
        'decision': decision,
        'writes': writes,
        'freeze_written': freeze_written,
        'freeze_until_ts': freeze_until_ts,
        'relay1_active': get_bool(ENT['surplus_r1_active']),
        'ev_active': get_bool(ENT['surplus_ev_active']),
        'relay2_active': get_bool(ENT['surplus_r2_active']),
    })
