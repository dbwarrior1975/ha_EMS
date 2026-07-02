from ems_core.domain.ev_power import ev_max_power_w, ev_min_power_w
from ems_core.domain.models import SurplusDeviceTarget


def _device_kind(cfg, device_id):
    if hasattr(cfg, 'device_kind'):
        return str(cfg.device_kind(device_id) or '')
    device = cfg.device_by_id(device_id) if hasattr(cfg, 'device_by_id') else None
    if device is None:
        return ''
    return str(getattr(device, 'kind', '') or '')


def _device_capability(cfg, device_id, field, default=None):
    if hasattr(cfg, 'device_capability'):
        return cfg.device_capability(device_id, field, default)
    device = cfg.device_by_id(device_id) if hasattr(cfg, 'device_by_id') else None
    if device is None:
        return default
    capabilities = getattr(device, 'capabilities', None)
    if capabilities is None:
        return default
    return getattr(capabilities, field, default)


def _ev_incremental_surplus_threshold_w(cfg, device_id, device):
    if device is not None and str(getattr(device, 'kind', '')) == 'EV_CHARGER':
        capabilities = device.capabilities
        min_absorb_w = float(getattr(capabilities, 'min_absorb_w', 0) or 0)
        max_absorb_w = float(getattr(capabilities, 'max_absorb_w', 0) or 0)
        return max(int(round(max_absorb_w - min_absorb_w)), 0)
    if _device_kind(cfg, device_id) == 'EV_CHARGER':
        min_absorb_w = float(_device_capability(cfg, device_id, 'min_absorb_w', 0) or 0)
        max_absorb_w = float(_device_capability(cfg, device_id, 'max_absorb_w', 0) or 0)
        return max(int(round(max_absorb_w - min_absorb_w)), 0)
    return max(int(ev_max_power_w(cfg) - ev_min_power_w(cfg)), 0)


def _adjustable_threshold_w(cfg, adjustable_device_id):
    configured_activation_w = float(getattr(cfg, 'adjustable_surplus_activation', 0.0) or 0.0)
    if configured_activation_w > 0.0:
        threshold_w = max(int(round(configured_activation_w)), 0)
        return threshold_w, 'configured_adjustable_surplus_activation_w', None
    device = None
    if not hasattr(cfg, 'device_kind') and hasattr(cfg, 'device_by_id'):
        device = cfg.device_by_id(adjustable_device_id)
    is_ev = (
        _device_kind(cfg, adjustable_device_id) == 'EV_CHARGER'
        or adjustable_device_id == 'EV_CHARGER'
        or (device is not None and str(getattr(device, 'kind', '')) == 'EV_CHARGER')
    )
    if is_ev:
        threshold_w = _ev_incremental_surplus_threshold_w(cfg, adjustable_device_id, device)
        return threshold_w, 'ev_incremental_max_minus_min_absorb_w', threshold_w
    threshold_w = max(int(round(float(cfg.max_solar_charge_w))), 0)
    return threshold_w, 'max_solar_charge_w', None


def build_surplus_device_targets(
    cfg,
    *,
    adjustable_device_id,
    adjustable_priority,
    adjustable_active,
    adjustable_enabled=True,
    relay_candidates=None,
):
    threshold_w, threshold_source, incremental_surplus_threshold_w = _adjustable_threshold_w(
        cfg,
        adjustable_device_id,
    )
    targets = [
        SurplusDeviceTarget(
            device_id=str(adjustable_device_id),
            decision_name='ADJUSTABLE',
            priority=int(adjustable_priority),
            rank=1,
            threshold_w=threshold_w,
            enabled=bool(adjustable_enabled),
            force_on=False,
            active=bool(adjustable_active),
            threshold_source=threshold_source,
            incremental_surplus_threshold_w=incremental_surplus_threshold_w,
        )
    ]
    relay_candidates = tuple(relay_candidates or ())
    next_rank = 2
    for relay in relay_candidates:
        device_id = str(relay.get('device_id') or '')
        threshold_w = max(int(round(float(relay.get('threshold_w', 0) or 0))), 0)
        if not device_id:
            continue
        targets.append(
            SurplusDeviceTarget(
                device_id=device_id,
                decision_name=device_id,
                priority=int(relay.get('priority', 0) or 0),
                rank=next_rank,
                threshold_w=threshold_w,
                enabled=bool(relay.get('enabled', True)),
                force_on=bool(relay.get('force_on', False)),
                active=bool(relay.get('active', False)),
                threshold_source='relay_threshold_w',
            )
        )
        next_rank += 1
    return tuple(targets)

def decision_name_for_device_id(targets, device_id):
    for target in targets:
        if target.device_id == device_id:
            return target.decision_name
    return ''


def device_targets_payload(targets):
    payload = []
    for target in targets:
        payload.append(
            {
                'device_id': target.device_id,
                'decision_name': target.decision_name,
                'priority': int(target.priority),
                'rank': int(target.rank),
                'threshold_w': int(target.threshold_w),
                'enabled': bool(target.enabled),
                'force_on': bool(target.force_on),
                'active': bool(target.active),
                'threshold_source': str(target.threshold_source or ''),
            }
        )
        if target.incremental_surplus_threshold_w is not None:
            payload[-1]['incremental_surplus_threshold_w'] = int(target.incremental_surplus_threshold_w)
    return payload
