from ems_core.domain.ev_power import ev_max_power_w, ev_min_power_w
from ems_core.domain.models import SurplusDeviceTarget, SurplusTargetConfig, SurplusDispatchDecision


def _ev_absorb_range_w(cfg, device):
    if device is not None and str(getattr(device, 'kind', '')) == 'EV_CHARGER':
        adapter = device.adapter
        phases = max(1, int(round(float(adapter.phases))))
        min_a = max(0, int(round(float(adapter.current_min_a))))
        max_a = max(min_a, int(round(float(adapter.current_max_a))))
        return max((max_a - min_a) * phases * 230, 0)
    return max(int(ev_max_power_w(cfg) - ev_min_power_w(cfg)), 0)


def _adjustable_threshold_w(cfg, adjustable_device_id):
    configured_activation_w = float(getattr(cfg, 'adjustable_surplus_activation', 0.0) or 0.0)
    if configured_activation_w > 0.0:
        return max(int(round(configured_activation_w)), 0)
    device = cfg.device_by_id(adjustable_device_id) if hasattr(cfg, 'device_by_id') else None
    is_ev = (
        adjustable_device_id == 'EV_CHARGER'
        or (device is not None and str(getattr(device, 'kind', '')) == 'EV_CHARGER')
    )
    if is_ev:
        return _ev_absorb_range_w(cfg, device)
    return max(int(round(float(cfg.max_solar_charge_w))), 0)


def build_surplus_device_targets(
    cfg,
    *,
    adjustable_device_id,
    adjustable_priority,
    adjustable_active,
    adjustable_enabled=True,
    relay_candidates=None,
):
    targets = [
        SurplusDeviceTarget(
            device_id=str(adjustable_device_id),
            decision_name='ADJUSTABLE',
            priority=int(adjustable_priority),
            rank=1,
            threshold_w=_adjustable_threshold_w(cfg, adjustable_device_id),
            enabled=bool(adjustable_enabled),
            force_on=False,
            active=bool(adjustable_active),
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
            )
        )
        next_rank += 1
    return tuple(targets)


def device_target_to_legacy_target(target):
    return SurplusTargetConfig(
        name=target.decision_name,
        priority=int(target.priority),
        rank=int(target.rank),
        threshold_kw=float(target.threshold_w) / 1000.0,
        enabled=bool(target.enabled),
        force_on=bool(target.force_on),
        active=bool(target.active),
    )


def device_targets_to_legacy_targets(targets):
    legacy_targets = []
    for target in targets:
        legacy_targets.append(device_target_to_legacy_target(target))
    return tuple(legacy_targets)


def decision_name_for_device_id(targets, device_id):
    for target in targets:
        if target.device_id == device_id:
            return target.decision_name
    return ''


def device_dispatch_to_legacy_dispatch(decision, targets):
    activate = decision_name_for_device_id(targets, decision.activate) if decision.activate else None
    release = decision_name_for_device_id(targets, decision.release) if decision.release else None
    explanation = decision.explanation
    for target in targets:
        explanation = explanation.replace(target.device_id, target.decision_name)
    return SurplusDispatchDecision(
        activate=activate,
        release=release,
        clear_all=bool(decision.clear_all),
        freeze_until_ts=decision.freeze_until_ts,
        explanation=explanation,
    )


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
            }
        )
    return payload
