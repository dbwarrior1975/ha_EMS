from ems_core.domain.models import SurplusDeviceTarget


def build_surplus_candidates(candidate_contexts=None):
    """Build one strict-priority target stack from generic device contexts.

    The caller owns eligibility. This module intentionally does not inspect device kind
    or any role alias names.
    """
    targets = []
    for rank, candidate in enumerate(tuple(candidate_contexts or ()), start=1):
        device_id = str(candidate.get('device_id') or '')
        if not device_id:
            continue
        threshold_w = max(int(round(float(candidate.get('threshold_w', 0) or 0))), 0)
        targets.append(
            SurplusDeviceTarget(
                device_id=device_id,
                priority=int(candidate.get('priority', 0) or 0),
                rank=rank,
                threshold_w=threshold_w,
                enabled=bool(candidate.get('enabled', True)),
                force_on=bool(candidate.get('force_on', False)),
                active=bool(candidate.get('active', False)),
                activation_allowed=bool(candidate.get('activation_allowed', True)),
                surplus_dispatch_mode=str(candidate.get('surplus_dispatch_mode') or ''),
                threshold_source=str(candidate.get('threshold_source') or 'device_capabilities.max_absorb_w'),
            )
        )
    return tuple(targets)



def candidate_payload(targets):
    payload = []
    for target in targets:
        payload.append(
            {
                'device_id': target.device_id,
                'priority': int(target.priority),
                'rank': int(target.rank),
                'threshold_w': int(target.threshold_w),
                'enabled': bool(target.enabled),
                'force_on': bool(target.force_on),
                'active': bool(target.active),
                'activation_allowed': bool(target.activation_allowed),
                'surplus_dispatch_mode': str(target.surplus_dispatch_mode or ''),
                'threshold_source': str(target.threshold_source or ''),
            }
        )
        if target.incremental_surplus_threshold_w is not None:
            payload[-1]['incremental_surplus_threshold_w'] = int(target.incremental_surplus_threshold_w)
    return payload
