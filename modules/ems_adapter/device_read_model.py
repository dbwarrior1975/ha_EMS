from typing import Union

from ems_core.domain.models import CoreConfig, EmsConfig, EmsDevice, EmsDeviceConfig, EmsDeviceState, RuntimeMeasurements
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


def _kw_to_w(power_kw):
    return int(round(float(power_kw) * 1000.0))


def _is_core_config(cfg):
    return isinstance(cfg, CoreConfig)


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
                step_w=max(1, int(round(float(capabilities.step_w)))),
                priority=int(round(float(policy.priority))),
            )
        )
    return tuple(mapped)


def _device_configs_from_legacy_config(cfg):
    return (
        EmsDeviceConfig(
            device_id=_BATTERY_ID,
            kind='BATTERY',
            response_kind='continuous',
            can_absorb_w=True,
            can_produce_w=True,
            min_absorb_w=0,
            max_absorb_w=int(round(float(cfg.max_solar_charge_w))),
            max_produce_w=int(round(float(cfg.max_battery_discharge_w))),
            step_w=max(1, int(round(float(cfg.deadband_w)))),
            priority=int(cfg.adjustable_surplus_load_priority),
        ),
        EmsDeviceConfig(
            device_id=_EV_ID,
            kind='EV_CHARGER',
            response_kind='selector',
            can_absorb_w=True,
            can_produce_w=False,
            min_absorb_w=ev_min_power_w(cfg),
            max_absorb_w=ev_max_power_w(cfg),
            max_produce_w=0,
            step_w=max(1, ev_power_step_w(cfg)),
            priority=int(cfg.ev_priority),
        ),
        EmsDeviceConfig(
            device_id=_RELAY1_ID,
            kind='RELAY',
            response_kind='relay',
            can_absorb_w=True,
            can_produce_w=False,
            min_absorb_w=_kw_to_w(cfg.relay1_power_kw),
            max_absorb_w=_kw_to_w(cfg.relay1_power_kw),
            max_produce_w=0,
            step_w=max(1, _kw_to_w(cfg.relay1_power_kw)),
            priority=int(cfg.relay1_priority),
        ),
        EmsDeviceConfig(
            device_id=_RELAY2_ID,
            kind='RELAY',
            response_kind='relay',
            can_absorb_w=True,
            can_produce_w=False,
            min_absorb_w=_kw_to_w(cfg.relay2_power_kw),
            max_absorb_w=_kw_to_w(cfg.relay2_power_kw),
            max_produce_w=0,
            step_w=max(1, _kw_to_w(cfg.relay2_power_kw)),
            priority=int(cfg.relay2_priority),
        ),
    )


def build_device_configs(cfg: Union[EmsConfig, CoreConfig]) -> tuple[EmsDeviceConfig, ...]:
    if _is_core_config(cfg):
        return _device_configs_from_core_config(cfg)
    return _device_configs_from_legacy_config(cfg)


def _battery_heartbeat_timeout_s(cfg):
    if _is_core_config(cfg):
        return float(cfg.battery_heartbeat_timeout_s)
    return float(cfg.battery_heartbeat_timeout_s)


def _ev_phases(cfg):
    if _is_core_config(cfg):
        ev_device = cfg.first_device_by_kind('EV_CHARGER') if hasattr(cfg, 'first_device_by_kind') else None
        if ev_device is not None:
            return int(round(float(ev_device.adapter.phases)))
        return int(round(float(getattr(cfg, 'ev_charger_phases', 1))))
    return int(cfg.ev_charger_phases)


def _relay_nominal_absorb_w(cfg, device_id):
    if _is_core_config(cfg):
        relay = cfg.device_by_id(device_id)
        if relay is None:
            return 0
        return int(round(float(relay.capabilities.max_absorb_w)))
    power_kw = cfg.relay1_power_kw if device_id == _RELAY1_ID else cfg.relay2_power_kw
    return _kw_to_w(power_kw)


def build_device_states(cfg: Union[EmsConfig, CoreConfig], m: RuntimeMeasurements) -> tuple[EmsDeviceState, ...]:
    if _is_core_config(cfg):
        return _build_device_states_from_core_config(cfg, m)

    battery_target_w = int(round(float(m.current_battery_setpoint_w)))
    battery_available = (
        m.soc is not None
        and float(m.battery_heartbeat_age_s) <= _battery_heartbeat_timeout_s(cfg)
    )
    ev_target_w = ev_current_a_to_power_w(
        m.charger_current_a if m.charger_on else 0,
        _ev_phases(cfg),
    )
    relay1_target_w = _relay_nominal_absorb_w(cfg, _RELAY1_ID) if m.relay1_on else 0
    relay2_target_w = _relay_nominal_absorb_w(cfg, _RELAY2_ID) if m.relay2_on else 0

    return (
        EmsDeviceState(
            device_id=_BATTERY_ID,
            available=battery_available,
            active=battery_target_w != 0,
            measured_power_w=battery_target_w,
            current_target_w=battery_target_w,
            guard_state='OK' if battery_available else 'STALE',
        ),
        EmsDeviceState(
            device_id=_EV_ID,
            available=True,
            active=bool(m.charger_on and int(m.charger_current_a) > 0),
            measured_power_w=ev_target_w,
            current_target_w=ev_target_w,
        ),
        EmsDeviceState(
            device_id=_RELAY1_ID,
            available=True,
            active=bool(m.relay1_on),
            measured_power_w=relay1_target_w,
            current_target_w=relay1_target_w,
        ),
        EmsDeviceState(
            device_id=_RELAY2_ID,
            available=True,
            active=bool(m.relay2_on),
            measured_power_w=relay2_target_w,
            current_target_w=relay2_target_w,
        ),
    )


def _build_device_states_from_core_config(cfg: CoreConfig, m: RuntimeMeasurements) -> tuple[EmsDeviceState, ...]:
    battery_target_w = int(round(float(m.current_battery_setpoint_w)))
    battery_available = (
        m.soc is not None
        and float(m.battery_heartbeat_age_s) <= _battery_heartbeat_timeout_s(cfg)
    )
    ev_target_w = ev_current_a_to_power_w(
        m.charger_current_a if m.charger_on else 0,
        _ev_phases(cfg),
    )

    states = []
    relay_devices = tuple(cfg.devices_by_kind('RELAY'))
    relay_state_map = dict(m.relay_states or {})
    legacy_relay_flags = {}
    for index, relay in enumerate(relay_devices[:2]):
        legacy_relay_flags[str(relay.device_id)] = bool(m.relay1_on if index == 0 else m.relay2_on)
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
            states.append(
                EmsDeviceState(
                    device_id=device_id,
                    available=True,
                    active=bool(m.charger_on and int(m.charger_current_a) > 0),
                    measured_power_w=ev_target_w,
                    current_target_w=ev_target_w,
                )
            )
            continue
        if kind == 'RELAY':
            relay_runtime = dict(relay_state_map.get(device_id, {}) or {})
            relay_on = relay_runtime.get('active')
            relay_available = bool(relay_runtime) or device_id in legacy_relay_flags
            if relay_on is None:
                relay_on = legacy_relay_flags.get(device_id, False)
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


def build_devices(cfg: Union[EmsConfig, CoreConfig], m: RuntimeMeasurements) -> tuple[EmsDevice, ...]:
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
