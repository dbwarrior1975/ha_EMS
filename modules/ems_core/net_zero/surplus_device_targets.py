from ems_core.domain.ev_power import ev_max_power_w, ev_min_power_w
from ems_core.domain.models import SurplusDeviceTarget, SurplusTargetConfig, SurplusDispatchDecision


def _adjustable_threshold_w(cfg, adjustable_device_id):
    configured_activation_w = float(getattr(cfg, 'adjustable_surplus_activation', 0.0) or 0.0)
    if configured_activation_w > 0.0:
        return max(int(round(configured_activation_w)), 0)
    if adjustable_device_id == 'EV_CHARGER':
        return max(int(ev_max_power_w(cfg) - ev_min_power_w(cfg)), 0)
    return max(int(round(float(cfg.max_solar_charge_w))), 0)


def build_surplus_device_targets(
    cfg,
    *,
    adjustable_device_id,
    adjustable_priority,
    adjustable_active,
    adjustable_enabled=True,
    relay1_enabled,
    relay1_force_on,
    relay1_active,
    relay1_capable=True,
    relay2_enabled,
    relay2_force_on,
    relay2_active,
    relay2_capable=True,
):
    return (
        SurplusDeviceTarget(
            device_id=str(adjustable_device_id),
            decision_name='ADJUSTABLE',
            priority=int(adjustable_priority),
            rank=1,
            threshold_w=_adjustable_threshold_w(cfg, adjustable_device_id),
            enabled=bool(adjustable_enabled),
            force_on=False,
            active=bool(adjustable_active),
        ),
        SurplusDeviceTarget(
            device_id='RELAY1',
            decision_name='RELAY1',
            priority=int(cfg.relay1_priority),
            rank=2,
            threshold_w=max(int(round(float(cfg.relay1_power_kw) * 1000.0)), 0),
            enabled=bool(relay1_enabled and relay1_capable),
            force_on=bool(relay1_force_on),
            active=bool(relay1_active),
        ),
        SurplusDeviceTarget(
            device_id='RELAY2',
            decision_name='RELAY2',
            priority=int(cfg.relay2_priority),
            rank=3,
            threshold_w=max(int(round(float(cfg.relay2_power_kw) * 1000.0)), 0),
            enabled=bool(relay2_enabled and relay2_capable),
            force_on=bool(relay2_force_on),
            active=bool(relay2_active),
        ),
    )


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
