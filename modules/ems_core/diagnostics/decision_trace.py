def net_zero_attrs(outputs, profiles, guard_decision=None):
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
        'ev_current_a': outputs.ev_current_a,
        'relay1_command': outputs.relay1_command,
        'relay2_command': outputs.relay2_command,
        'surplus_policy_active': outputs.surplus_policy_active,
        'surplus_next_target': outputs.surplus_next_target,
        'surplus_next_threshold_kw': outputs.surplus_next_threshold_kw,
        'surplus_release_candidate': outputs.surplus_release_candidate,
        'surplus_dispatch_decision': outputs.surplus_dispatch_decision,
        'surplus_explanation': outputs.surplus_explanation,
    }

    attrs.update(outputs.attrs)

    if guard_decision is not None:
        attrs['guard_reason'] = guard_decision.reason

    return attrs