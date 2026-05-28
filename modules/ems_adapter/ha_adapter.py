from datetime import datetime

def _state(entity_id, default=None):
    try:
        val = state.get(entity_id)
    except Exception:
        return default
    if val in (None, 'unknown', 'unavailable', 'none', ''):
        return default
    return val

def get_float(entity_id, default=0.0):
    try:
        return float(_state(entity_id, default))
    except Exception:
        return default

def get_int(entity_id, default=0):
    try:
        return int(float(_state(entity_id, default)))
    except Exception:
        return default

def get_bool(entity_id):
    return _state(entity_id, 'off') == 'on'

def get_str(entity_id, default=''):
    return str(_state(entity_id, default))

def age_seconds(entity_id, now_ts=None, fallback=999999.0):
    now_ts = now_ts or datetime.now().timestamp()
    try:
        s = state.get(entity_id)
        last = getattr(s, 'last_reported', None) or getattr(s, 'last_updated', None) or getattr(s, 'last_changed', None)
        if last is None:
            return fallback
        return now_ts - last.timestamp()
    except Exception:
        return fallback

def get_attr(entity_id, attr, default=None):
    try:
        return state.getattr(entity_id).get(attr, default)
    except Exception:
        return default

def publish_sensor(entity_id, value, attrs=None):
    state.set(entity_id, value=value, new_attributes=attrs or {})

def set_number(entity_id, value):
    input_number.set_value(entity_id=entity_id, value=value)

def set_boolean(entity_id, on):
    if on:
        input_boolean.turn_on(entity_id=entity_id)
    else:
        input_boolean.turn_off(entity_id=entity_id)

def parse_input_datetime_ts(entity_id):
    raw = _state(entity_id, None)
    if raw in (None, 'unknown', 'unavailable', 'none', ''):
        return None
    try:
        return datetime.fromisoformat(str(raw)).timestamp()
    except Exception:
        try:
            return datetime.strptime(str(raw), '%Y-%m-%d %H:%M:%S').timestamp()
        except Exception:
            return None
