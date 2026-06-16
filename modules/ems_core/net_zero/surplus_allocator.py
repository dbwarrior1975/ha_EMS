from ems_core.domain.models import SurplusDispatchDecision


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


def _highest_priority_candidate(targets, threshold_attr):
    selected = None
    for target in targets:
        threshold = getattr(target, threshold_attr)
        if target.priority > 0 and target.enabled and (not target.force_on) and (not target.active) and threshold > 0:
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


def active_stack(targets):
    active = _active_targets_priority_desc(targets)
    if not active:
        return 'NONE'
    names = []
    for t in active:
        names.append(t.name)
    return ' > '.join(names)

def next_target(targets):
    return _highest_priority_candidate(targets, 'threshold_kw')

def release_target(targets):
    return _lowest_priority_active(targets)


def active_device_stack(targets):
    active = _active_targets_priority_desc(targets)
    if not active:
        return 'NONE'
    device_ids = []
    for t in active:
        device_ids.append(t.device_id)
    return ' > '.join(device_ids)


def next_device_target(targets):
    return _highest_priority_candidate(targets, 'threshold_w')


def release_device_target(targets):
    return _lowest_priority_active(targets)

def compute_surplus_dispatch(inp, now_ts, freeze_s=30):
    if not inp.policy_active:
        return SurplusDispatchDecision(clear_all=True, freeze_until_ts=now_ts, explanation='Policy inactive -> clear all surplus states')
    for t in inp.targets:
        if t.active and ((not t.enabled) or t.force_on):
            return SurplusDispatchDecision(release=t.name, explanation=f'{t.name} no longer eligible -> release dispatch state')
    active = []
    for t in inp.targets:
        if t.active and t.priority > 0:
            active.append(t)
    if inp.rpnz_w <= 0 and active:
        rel = release_target(inp.targets)
        return SurplusDispatchDecision(release=rel.name, explanation='RPNZ <= 0 -> release lowest-priority active target')
    if inp.freeze_until_ts is not None and inp.freeze_until_ts > now_ts:
        return SurplusDispatchDecision(explanation='Freeze active -> wait for measurements to settle')
    nxt = next_target(inp.targets)
    if not nxt:
        return SurplusDispatchDecision(explanation='No eligible next surplus target')
    if inp.rpc_kw >= nxt.threshold_kw:
        return SurplusDispatchDecision(activate=nxt.name, freeze_until_ts=now_ts + freeze_s, explanation=f'Raw RPC {inp.rpc_kw:.3f} kW >= {nxt.name} threshold {nxt.threshold_kw:.3f} kW')
    return SurplusDispatchDecision(explanation=f'Waiting for {nxt.name}; raw RPC below threshold')


def compute_surplus_device_dispatch(inp, now_ts, freeze_s=30):
    if not inp.policy_active:
        return SurplusDispatchDecision(clear_all=True, freeze_until_ts=now_ts, explanation='Policy inactive -> clear all surplus states')
    for target in inp.targets:
        if target.active and ((not target.enabled) or target.force_on):
            return SurplusDispatchDecision(release=target.device_id, explanation=f'{target.device_id} no longer eligible -> release dispatch state')
    active = []
    for target in inp.targets:
        if target.active and target.priority > 0:
            active.append(target)
    if inp.rpnz_w <= 0 and active:
        release = release_device_target(inp.targets)
        return SurplusDispatchDecision(release=release.device_id, explanation='RPNZ <= 0 -> release lowest-priority active target')
    if inp.freeze_until_ts is not None and inp.freeze_until_ts > now_ts:
        return SurplusDispatchDecision(explanation='Freeze active -> wait for measurements to settle')
    nxt = next_device_target(inp.targets)
    if not nxt:
        return SurplusDispatchDecision(explanation='No eligible next surplus target')
    threshold_kw = float(nxt.threshold_w) / 1000.0
    if inp.rpc_kw >= threshold_kw:
        return SurplusDispatchDecision(activate=nxt.device_id, freeze_until_ts=now_ts + freeze_s, explanation=f'Raw RPC {inp.rpc_kw:.3f} kW >= {nxt.device_id} threshold {threshold_kw:.3f} kW')
    return SurplusDispatchDecision(explanation=f'Waiting for {nxt.device_id}; raw RPC below threshold')
