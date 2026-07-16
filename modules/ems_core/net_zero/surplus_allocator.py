from ems_core.domain.models import SurplusDispatchDecision

RPNZ_PRACTICAL_ZERO_W = 10.0
SURPLUS_RELEASE_DEADBAND_W = RPNZ_PRACTICAL_ZERO_W
N_MINUS_ONE_RELEASE_MIN_MARGIN_W = 100.0
N_MINUS_ONE_RELEASE_MARGIN_FRACTION = 0.05


def _is_higher_priority_candidate(candidate, current):
    if current is None:
        return True
    if candidate.priority > current.priority:
        return True
    if candidate.priority == current.priority and candidate.rank < current.rank:
        return True
    return False


def _is_lower_priority_active(candidate, current):
    if current is None:
        return True
    if candidate.priority < current.priority:
        return True
    if candidate.priority == current.priority and candidate.rank > current.rank:
        return True
    return False


def _active_targets_priority_desc(targets):
    ordered = []
    for target in targets:
        if not (target.active and target.priority > 0):
            continue
        inserted = False
        index = 0
        while index < len(ordered):
            if _is_higher_priority_candidate(target, ordered[index]):
                ordered.insert(index, target)
                inserted = True
                break
            index += 1
        if not inserted:
            ordered.append(target)
    return ordered


def _active_targets_in_activation_order(targets, active_device_ids=()):
    """Return active targets oldest-first using persisted dispatch order.

    The dispatch state applier appends each ACTIVATE device ID to the persisted
    list and removes it on RELEASE. That order is therefore the canonical
    activation order. Older persisted states or direct unit callers may omit
    the list; active strict-priority order is then the deterministic fallback.
    """
    active_by_id = {}
    for target in targets:
        if target.active and target.priority > 0:
            active_by_id[str(target.device_id)] = target

    ordered = []
    seen = set()
    for raw_device_id in active_device_ids or ():
        device_id = str(raw_device_id or '')
        target = active_by_id.get(device_id)
        if target is None or device_id in seen:
            continue
        ordered.append(target)
        seen.add(device_id)

    for target in _active_targets_priority_desc(targets):
        device_id = str(target.device_id)
        if device_id in seen:
            continue
        ordered.append(target)
        seen.add(device_id)
    return ordered


def _highest_priority_candidate(targets, threshold_attr):
    selected = None
    for target in targets:
        threshold = getattr(target, threshold_attr)
        if target.priority > 0 and target.enabled and target.activation_allowed and (not target.force_on) and (not target.active) and threshold > 0:
            if _is_higher_priority_candidate(target, selected):
                selected = target
    return selected


def _lowest_priority_active(targets):
    selected = None
    for target in targets:
        if target.active and target.priority > 0:
            if _is_lower_priority_active(target, selected):
                selected = target
    return selected


def _release_power_w(target):
    configured = getattr(target, 'releasable_power_w', None)
    if configured is not None and float(configured) > 0.0:
        return max(int(round(float(configured))), 0)
    return max(int(round(float(getattr(target, 'threshold_w', 0) or 0))), 0)


def _release_margin_w(power_w):
    power_w = max(float(power_w), 0.0)
    return int(round(max(
        N_MINUS_ONE_RELEASE_MIN_MARGIN_W,
        N_MINUS_ONE_RELEASE_MARGIN_FRACTION * power_w,
    )))


def active_device_stack(targets):
    active = _active_targets_priority_desc(targets)
    if not active:
        return 'NONE'
    device_ids = []
    for target in active:
        device_ids.append(target.device_id)
    return ' > '.join(device_ids)


def next_device_target(targets):
    return _highest_priority_candidate(targets, 'threshold_w')


def release_device_target(targets, active_device_ids=()):
    active = _active_targets_in_activation_order(targets, active_device_ids)
    if active:
        return active[-1]
    return _lowest_priority_active(targets)


def compute_surplus_device_dispatch(inp, now_ts, freeze_s=30):
    if not inp.policy_active:
        return SurplusDispatchDecision(
            clear_all=True,
            freeze_until_ts=now_ts,
            explanation='Policy inactive -> clear all surplus states',
        )

    for target in inp.targets:
        if target.active and ((not target.enabled) or (not target.activation_allowed) or target.force_on or target.priority <= 0):
            return SurplusDispatchDecision(
                release=target.device_id,
                explanation=f'{target.device_id} no longer eligible -> release dispatch state',
                release_mode='ineligible',
            )

    active = _active_targets_in_activation_order(
        inp.targets,
        getattr(inp, 'active_device_ids', ()) or (),
    )

    # Every optimizer-owned activation/release observes the measurement-settle
    # freeze. Ineligible active targets remain the only fail-closed exception.
    if inp.freeze_until_ts is not None and inp.freeze_until_ts > now_ts:
        return SurplusDispatchDecision(
            explanation='Freeze active -> wait for measurements to settle'
        )

    # The oldest/anchor device retains the established conservative RPNZ
    # release rule. Additional n-1 load steps are released only by the
    # incremental excess-consumption rule below.
    if len(active) == 1 and inp.rpnz_w <= SURPLUS_RELEASE_DEADBAND_W:
        release = active[0]
        return SurplusDispatchDecision(
            release=release.device_id,
            explanation='RPNZ <= 10 W release deadband -> release lowest-priority active target',
            release_mode='anchor_rpnz_deadband',
        )

    if len(active) > 1:
        release = active[-1]
        release_power_w = _release_power_w(release)
        release_margin_w = _release_margin_w(release_power_w)
        release_threshold_w = max(release_power_w - release_margin_w, 0)
        excess_consumption_w = max(int(round(-float(inp.rpc_kw) * 1000.0)), 0)
        if release_power_w > 0 and excess_consumption_w >= release_threshold_w:
            return SurplusDispatchDecision(
                release=release.device_id,
                freeze_until_ts=float(now_ts) + float(freeze_s),
                explanation=(
                    f'N-1 excess {excess_consumption_w} W >= {release.device_id} '
                    f'release threshold {release_threshold_w} W '
                    f'({release_power_w} W - {release_margin_w} W margin)'
                ),
                release_mode='n_minus_one_incremental',
                release_power_w=release_power_w,
                release_margin_w=release_margin_w,
                release_threshold_w=release_threshold_w,
                excess_consumption_w=excess_consumption_w,
            )
        if float(inp.rpc_kw) < 0.0:
            return SurplusDispatchDecision(
                explanation=(
                    f'Holding {release.device_id}; excess {excess_consumption_w} W '
                    f'below N-1 release threshold {release_threshold_w} W'
                ),
                release_mode='n_minus_one_hold',
                release_power_w=release_power_w,
                release_margin_w=release_margin_w,
                release_threshold_w=release_threshold_w,
                excess_consumption_w=excess_consumption_w,
            )

    nxt = next_device_target(inp.targets)
    if not nxt:
        return SurplusDispatchDecision(explanation='No eligible next surplus target')
    threshold_kw = float(nxt.threshold_w) / 1000.0
    if inp.rpc_kw >= threshold_kw:
        return SurplusDispatchDecision(
            activate=nxt.device_id,
            freeze_until_ts=now_ts + freeze_s,
            explanation=(
                f'Raw RPC {inp.rpc_kw:.3f} kW >= '
                f'{nxt.device_id} threshold {threshold_kw:.3f} kW'
            ),
        )
    return SurplusDispatchDecision(
        explanation=f'Waiting for {nxt.device_id}; raw RPC below threshold'
    )
