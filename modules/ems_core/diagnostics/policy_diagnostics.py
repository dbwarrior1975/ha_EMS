def net_zero_attrs(outputs, profiles, guard_decision=None):
    device_policy_payloads = outputs.attrs.get('device_policies')
    if not device_policy_payloads and getattr(outputs, 'device_policies', ()):
        payloads = []
        for policy in outputs.device_policies:
            payload = {
                'device_id': policy.device_id,
                'target_w': int(policy.target_w),
                'enabled': bool(policy.enabled),
                'mode': policy.mode,
                'reason': policy.reason,
            }
            payloads.append(payload)
        device_policy_payloads = tuple(payloads)

    attrs = {
        'control': profiles.control,
        'goal': profiles.goal,
        'forecast_profile': profiles.forecast,
        'guard': profiles.guard,
        'effective_forecast': outputs.effective_forecast,
        'dominant_limitation': outputs.dominant_limitation,
        'explanation': outputs.explanation,
        'battery_target_w': outputs.battery_target_w,
        'battery_write_enabled': outputs.battery_write_enabled,
        'surplus_policy_active': outputs.surplus_policy_active,
        'surplus_next_target': outputs.surplus_next_target,
        'surplus_next_threshold_kw': outputs.surplus_next_threshold_kw,
        'surplus_release_candidate': outputs.surplus_release_candidate,
        'surplus_dispatch_decision': outputs.surplus_dispatch_decision,
        'surplus_explanation': outputs.surplus_explanation,
        'device_policies': device_policy_payloads or (),
    }

    attrs.update(outputs.attrs)

    if guard_decision is not None:
        attrs['guard_reason'] = guard_decision.reason

    return attrs
