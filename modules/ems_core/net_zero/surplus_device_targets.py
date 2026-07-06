from ems_core.domain.models import SurplusDeviceTarget


def _adjustable_threshold_w(cfg, adjustable_device_id):
    configured_activation_w = float(cfg.adjustable_surplus_activation)
    threshold_w = int(round(configured_activation_w))
    return threshold_w, 'configured_adjustable_surplus_activation_w', None


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
