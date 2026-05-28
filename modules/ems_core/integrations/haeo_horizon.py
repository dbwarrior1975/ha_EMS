from datetime import datetime

def _to_ts(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except ValueError:
            return None
    return None

def latest_forecast_value_at_or_before(forecast, now_ts, default=0.0):
    best_ts = -1.0
    best_value = None
    for entry in forecast or []:
        t = entry.get('time') if hasattr(entry, 'get') else getattr(entry, 'time', None)
        v = entry.get('value') if hasattr(entry, 'get') else getattr(entry, 'value', None)
        ts = _to_ts(t)
        if ts is not None and ts <= now_ts and ts > best_ts:
            best_ts = ts
            try:
                best_value = float(v)
            except (TypeError, ValueError):
                best_value = None
    return default if best_value is None else best_value

def ev_kw_to_selector_current_a(kw, phases, max_a, allowed=(4,8,12,16,20,24,28,32)):
    raw_a = (float(kw) * 1000.0) / (max(phases, 1) * 230.0)
    if raw_a < 1:
        return 0
    candidates = [a for a in allowed if a <= max_a]
    if not candidates:
        return 0
    best = candidates[0]
    bestdiff = abs(raw_a - best)
    for a in candidates[1:]:
        d = abs(raw_a - a)
        if d < bestdiff:
            best, bestdiff = a, d
    return int(best)
