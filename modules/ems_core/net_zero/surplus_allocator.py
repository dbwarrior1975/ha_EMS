from ems_core.domain.models import SurplusDispatchDecision

def active_stack(targets):
    active = [t for t in targets if t.active and t.priority > 0]
    if not active:
        return 'NONE'
    active = sorted(active, key=lambda t: (-t.priority, t.rank))
    return ' > '.join([t.name for t in active])

def next_target(targets):
    candidates = [t for t in targets if t.priority > 0 and t.enabled and (not t.force_on) and (not t.active) and t.threshold_kw > 0]
    if not candidates:
        return None
    return sorted(candidates, key=lambda t: (-t.priority, t.rank))[0]

def release_target(targets):
    active = [t for t in targets if t.active and t.priority > 0]
    if not active:
        return None
    return sorted(active, key=lambda t: (t.priority, -t.rank))[0]

def compute_surplus_dispatch(inp, now_ts, freeze_s=30):
    if not inp.policy_active:
        return SurplusDispatchDecision(clear_all=True, freeze_until_ts=now_ts, explanation='Policy inactive -> clear all surplus states')
    for t in inp.targets:
        if t.active and ((not t.enabled) or t.force_on):
            return SurplusDispatchDecision(release=t.name, explanation=f'{t.name} no longer eligible -> release dispatch state')
    active = [t for t in inp.targets if t.active and t.priority > 0]
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
