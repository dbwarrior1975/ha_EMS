from ems_core.domain.models import EmsDeviceConfig


def can_absorb(device_config):
    return bool(getattr(device_config, 'can_absorb_w', False))


def can_produce(device_config):
    return bool(getattr(device_config, 'can_produce_w', False))


def clamp_target_w_for_capabilities(device_config, target_w):
    target = int(round(float(target_w)))
    if target > 0:
        if not can_absorb(device_config):
            return 0
        max_absorb_w = max(int(getattr(device_config, 'max_absorb_w', 0) or 0), 0)
        return min(target, max_absorb_w)
    if target < 0:
        if not can_produce(device_config):
            return 0
        max_produce_w = max(int(getattr(device_config, 'max_produce_w', 0) or 0), 0)
        return max(target, -max_produce_w)
    return 0


def capability_block_reason(device_config, target_w):
    target = int(round(float(target_w)))
    if target > 0 and not can_absorb(device_config):
        return 'capability_blocked_absorb'
    if target < 0 and not can_produce(device_config):
        return 'capability_blocked_produce'
    return ''
