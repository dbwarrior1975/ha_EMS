from ems_core.domain.models import CoreConfig, EmsDevice, EmsDeviceConfig, EmsDeviceState, RuntimeMeasurements
from ems_core.domain.ev_power import (
    ev_current_a_to_power_w,
    ev_max_power_w,
    ev_min_power_w,
    ev_power_step_w,
)

_BATTERY_ID = 'HOME_BATTERY'
_EV_ID = 'EV_CHARGER'
_RELAY1_ID = 'RELAY1'
_RELAY2_ID = 'RELAY2'


def _response_kind_for_device(device_id, kind):
    if device_id == _BATTERY_ID or str(kind) == 'BATTERY':
        return 'continuous'
    if device_id == _EV_ID or str(kind) == 'EV_CHARGER':
        return 'selector'
    return 'relay'


def _device_configs_from_core_config(cfg):
    devices = tuple(cfg.devices.values())
    mapped = []
    for device in devices:
        capabilities = device.capabilities
        policy = device.policy
        step_w = max(1, int(round(float(capabilities.step_w))))
        if str(device.kind) == 'EV_CHARGER':
            step_w = max(
                1,
                int(
                    round(
                        ev_current_a_to_power_w(
                            device.adapter.current_step_a,
                            device.adapter.phases,
                            device.adapter.voltage_v,
                        )
                    )
                ),
            )
        mapped.append(
            EmsDeviceConfig(
                device_id=str(device.device_id),
                kind=str(device.kind),
                response_kind=_response_kind_for_device(device.device_id, device.kind),
                can_absorb_w=bool(capabilities.can_absorb_w),
                can_produce_w=bool(capabilities.can_produce_w),
                min_absorb_w=int(round(float(capabilities.min_absorb_w))),
                max_absorb_w=int(round(float(capabilities.max_absorb_w))),
                max_produce_w=int(round(float(capabilities.max_produce_w or 0))),
                step_w=step_w,
                priority=int(round(float(policy.priority))),
            )
        )
    return tuple(mapped)


def build_device_configs(cfg: CoreConfig) -> tuple[EmsDeviceConfig, ...]:
    return _device_configs_from_core_config(cfg)


def _battery_heartbeat_timeout_s(cfg):
    return float(cfg.battery_heartbeat_timeout_s)


def _ev_adapter_int(value, default):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return int(default)


def _ev_adapter_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _relay_nominal_absorb_w(cfg, device_id):
    relay = cfg.device_by_id(device_id)
    if relay is None:
        return 0
    return int(round(float(relay.capabilities.max_absorb_w)))


def _ev_runtime_state(m: RuntimeMeasurements, device_id: str) -> dict:
    return dict((m.ev_states or {}).get(str(device_id), {}) or {})


def _relay_runtime_state(m: RuntimeMeasurements, device_id: str) -> dict:
    return dict((m.relay_states or {}).get(str(device_id), {}) or {})


def build_device_states(cfg: CoreConfig, m: RuntimeMeasurements) -> tuple[EmsDeviceState, ...]:
    return _build_device_states_from_core_config(cfg, m)


def build_device_measured_power_w_by_id(cfg: CoreConfig, m: RuntimeMeasurements) -> dict[str, float]:
    measured = {}
    devices = getattr(cfg, 'devices', {}) or {}
    if not hasattr(devices, 'values'):
        return measured
    for device in devices.values():
        device_id = str(device.device_id)
        kind = str(device.kind)
        if device_id == _BATTERY_ID or kind == 'BATTERY':
            measured[device_id] = float(m.current_battery_setpoint_w)
            continue
        if kind == 'EV_CHARGER':
            ev_runtime = _ev_runtime_state(m, device_id)
            ev_current_a = int(ev_runtime.get('current_a', 0) or 0)
            measured[device_id] = float(
                ev_current_a_to_power_w(
                    ev_current_a,
                    _ev_adapter_int(getattr(device.adapter, 'phases', None), 1),
                    _ev_adapter_float(getattr(device.adapter, 'voltage_v', None), 230.0),
                )
            )
            continue
        if kind == 'RELAY':
            relay_runtime = _relay_runtime_state(m, device_id)
            measured[device_id] = float(
                _relay_nominal_absorb_w(cfg, device_id) if relay_runtime.get('active') else 0
            )
            continue
        measured[device_id] = 0.0
    return measured


def _build_device_states_from_core_config(cfg: CoreConfig, m: RuntimeMeasurements) -> tuple[EmsDeviceState, ...]:
    battery_target_w = int(round(float(m.current_battery_setpoint_w)))
    battery_available = (
        m.soc is not None
        and float(m.battery_heartbeat_age_s) <= _battery_heartbeat_timeout_s(cfg)
    )

    states = []
    for device in cfg.devices.values():
        device_id = str(device.device_id)
        kind = str(device.kind)
        if device_id == _BATTERY_ID or kind == 'BATTERY':
            states.append(
                EmsDeviceState(
                    device_id=device_id,
                    available=battery_available,
                    active=battery_target_w != 0,
                    measured_power_w=battery_target_w,
                    current_target_w=battery_target_w,
                    guard_state='OK' if battery_available else 'STALE',
                )
            )
            continue
        if kind == 'EV_CHARGER':
            ev_runtime = _ev_runtime_state(m, device_id)
            ev_enabled = bool(ev_runtime.get('enabled', False))
            ev_current_a = int(ev_runtime.get('current_a', 0) or 0)
            ev_phases = _ev_adapter_int(getattr(device.adapter, 'phases', None), 1)
            ev_voltage_v = _ev_adapter_float(getattr(device.adapter, 'voltage_v', None), 230.0)
            ev_target_w = ev_current_a_to_power_w(
                ev_current_a if ev_enabled else 0,
                ev_phases,
                ev_voltage_v,
            )
            states.append(
                EmsDeviceState(
                    device_id=device_id,
                    available=bool(ev_runtime),
                    active=bool(ev_enabled and ev_current_a > 0),
                    measured_power_w=ev_target_w,
                    current_target_w=ev_target_w,
                    guard_state='OK' if ev_runtime else 'UNWIRED',
                )
            )
            continue
        if kind == 'RELAY':
            relay_runtime = _relay_runtime_state(m, device_id)
            relay_on = relay_runtime.get('active')
            relay_available = bool(relay_runtime)
            if relay_on is None:
                relay_on = False
            relay_target_w = _relay_nominal_absorb_w(cfg, device_id) if relay_on else 0
            states.append(
                EmsDeviceState(
                    device_id=device_id,
                    available=relay_available,
                    active=bool(relay_on),
                    measured_power_w=relay_target_w,
                    current_target_w=relay_target_w,
                    guard_state='OK' if relay_available else 'UNWIRED',
                )
            )
            continue
        states.append(
            EmsDeviceState(
                device_id=device_id,
                available=False,
                active=False,
                measured_power_w=0,
                current_target_w=0,
                guard_state='UNWIRED',
            )
        )
    return tuple(states)


def build_devices(cfg: CoreConfig, m: RuntimeMeasurements) -> tuple[EmsDevice, ...]:
    state_by_id = {}
    for state in build_device_states(cfg, m):
        state_by_id[state.device_id] = state
    devices = []
    for device_config in build_device_configs(cfg):
        state = state_by_id.get(device_config.device_id)
        if state is None:
            state = EmsDeviceState(
                device_id=device_config.device_id,
                available=False,
                active=False,
                measured_power_w=0,
                current_target_w=0,
                guard_state='UNWIRED',
            )
        devices.append(EmsDevice(config=device_config, state=state))
    return tuple(devices)
