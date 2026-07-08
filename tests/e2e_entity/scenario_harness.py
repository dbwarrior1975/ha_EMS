from __future__ import annotations

import copy
import os
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from ems_adapter.config_loader import load_grouped_ems_config
from ems_adapter.runtime_context import build_runtime_entities_from_grouped_config
from tests.e2e_entity.scenario_runner import seed_active_surplus_devices
from tests.e2e_entity.net_zero_inputs import runtime_inputs_for_net_zero_intent


class FakeEntityStore:
    def __init__(self):
        self.values = {}
        self.attrs = {}
        self.last_update_ts = {}
        self.now = 0.0

    def set_now(self, now_ts: float):
        self.now = float(now_ts)

    def set_value(self, entity_id, value):
        self.values[entity_id] = value
        self.last_update_ts[entity_id] = self.now

    def set_attr(self, entity_id, attrs):
        self.attrs[entity_id] = attrs or {}
        self.last_update_ts[entity_id] = self.now

    def get_value(self, entity_id, default=None):
        return self.values.get(entity_id, default)

    def get_attr(self, entity_id, key=None, default=None):
        attrs = self.attrs.get(entity_id, {})
        if key is None:
            return attrs
        return attrs.get(key, default)


class QuarterScenarioHarness:
    """
    Grouped-config-driven quarter simulator for the current three-loop production chain:

        policy loop -> dispatch state applier loop -> writer loop

    This harness intentionally exercises the library the same way production does now:
    - dispatcher decisions are written by ems_policy_engine.py
    - ems_dispatch_state_applier.py converts dispatch decisions to active states/freeze state
    - ems_actuator_writers.py consumes policy outputs and updates actuator/policy entities
    """

    def __init__(
        self,
        project_root: Path,
        start_ts: float = 0.0,
        step_s: int = 30,
        cfg_overrides: dict | None = None,
        grouped_config_path: Path | None = None,
        scenario_dir: Path | None = None,
    ):
        self.project_root = Path(project_root)
        self.store = FakeEntityStore()
        self.now = float(start_ts)
        self.step_s = int(step_s)
        self.cfg_overrides = dict(cfg_overrides or {})
        self.history = []
        self.scenario_dir = Path(scenario_dir) if scenario_dir is not None else None
        self.grouped_config_path = self._resolve_grouped_config_path(
            project_root=self.project_root,
            grouped_config_path=grouped_config_path,
            scenario_dir=self.scenario_dir,
        )
        self.grouped_config = None
        self.ent = {}
        if self.grouped_config_path is not None and self.grouped_config_path.exists():
            self.grouped_config = load_grouped_ems_config(self.grouped_config_path)
            self.ent = build_runtime_entities_from_grouped_config(self.grouped_config)
        if self.grouped_config_path is not None:
            os.environ['EMS_GROUPED_CONFIG_PATH'] = str(self.grouped_config_path)

        self.policy_mod = self._load_module(self.project_root / 'ems_policy_engine.py', kind='policy')
        self.dispatch_state_applier_mod = self._load_module(
            self.project_root / 'ems_dispatch_state_applier.py',
            kind='dispatch_state_applier',
        )
        self.writer_mod = self._load_module(self.project_root / 'ems_actuator_writers.py', kind='writer')
        self._seed_defaults()

    def entity(self, key):
        return self.ent[key]

    def _entity_id(self, key):
        entity_id = self.ent.get(key)
        if not entity_id:
            raise KeyError(
                f"missing runtime entity key={key} config={self.grouped_config_path}"
            )
        return entity_id

    def _optional_entity_id(self, key):
        return self.ent.get(key)

    def _optional_device_entity_id(self, device_id, field):
        device = (self.ent.get('devices') or {}).get(device_id) or {}
        return device.get(field)

    def device_entity(self, device_id, field):
        device = (self.ent.get('devices') or {}).get(device_id) or {}
        entity_id = device.get(field)
        if not entity_id:
            raise KeyError(
                f"missing scenario runtime entity for device_id={device_id} field={field} "
                f"config={self.grouped_config_path}"
            )
        return entity_id

    def dev(self, device_id, field):
        return self.device_entity(device_id, field)

    @staticmethod
    def _resolve_grouped_config_path(
        *,
        project_root: Path,
        grouped_config_path: Path | None = None,
        scenario_dir: Path | None = None,
    ) -> Path | None:
        if grouped_config_path is not None:
            return Path(grouped_config_path)

        if scenario_dir is not None:
            scenario_path = Path(scenario_dir)
            candidate = scenario_path / 'EMS_config.yaml'
            if candidate.exists():
                return candidate
            raise FileNotFoundError(
                f"scenario_dir requires EMS_config.yaml: {scenario_path}"
            )

        env_grouped_path = os.environ.get('EMS_GROUPED_CONFIG_PATH', '').strip()
        if env_grouped_path:
            return Path(env_grouped_path)

        for filename in ('example_EMS_config.yaml', 'EMS_config.yaml'):
            candidate = Path(project_root) / filename
            if candidate.exists():
                return candidate

        return None

    def set_entities(self, mapping: dict):
        self.store.set_now(self.now)
        for entity_id, value in dict(mapping or {}).items():
            self.store.set_value(entity_id, value)
            self._sync_grouped_config_entities(entity_id, value)

    def set_attrs(self, entity_id: str, attrs: dict):
        self.store.set_now(self.now)
        self.store.set_attr(entity_id, attrs)

    def set_stale(self, entity_id: str, age_s: float):
        self.store.last_update_ts[entity_id] = float(self.now) - float(age_s)

    def get(self, entity_id, default=None):
        return self.store.get_value(entity_id, default)

    def getattrs(self, entity_id):
        return self.store.get_attr(entity_id)

    def snapshot(self, note: str = ''):
        return {
            't': self.now,
            'note': note,
            'values': copy.deepcopy(self.store.values),
            'attrs': copy.deepcopy(self.store.attrs),
        }

    def step(self, set_values: dict | None = None, note: str = '', at_s: float | None = None):
        if at_s is not None:
            self.now = float(at_s)
        self.store.set_now(self.now)
        if set_values:
            self.set_entities(set_values)

        self._run_policy_loop()
        self._run_dispatch_state_applier_loop()
        self._run_writer_loop()

        snap = self.snapshot(note=note)
        self.history.append(snap)
        if at_s is None:
            self.now += self.step_s
        self.store.set_now(self.now)
        return snap

    def _seed_defaults(self):
        if self.grouped_config is None:
            return
        self.store.set_now(self.now)
        default_specs = (
            ('control_profile', 'AUTOMATIC'),
            ('goal_profile', 'NET_ZERO'),
            ('forecast_profile', 'NONE'),
            ('guard_profile', 'NORMAL_LIMITS'),
            ('battery_protect_soc', 2),
            ('battery_protect_soc_recovery_margin', 1),
            ('battery_protect_min_cell_voltage_v', 3.03),
            ('deadband_w', 50),
            ('ramp_max_w', 1000),
            ('strict_limits_max_w', 4600),
            ('max_battery_discharge_w', 4600),
            ('max_solar_charge_w', 3700),
            ('ev_min_absorb_w', 1380),
            ('ev_max_absorb_w', 6440),
            ('ev_charger_phases', 1),
            ('ev_force_on', False),
            ('ev_current_step_a', 4),
            ('ev_hard_off_pv_threshold_kw', 1.6),
            ('ev_hard_off_low_pv_cycles', 2),
            ('ev_hard_off_release_cycles', 2),
            ('haeo_stale_timeout_s', 300),
            ('soc', 50.0),
            ('min_cell_voltage_v', 3.20),
            ('battery_heartbeat', 0.0),
            ('grid_power_w', 0.0),
            ('current_battery_sp', 100.0),
            ('quarter_energy_balance', 0.0),
            ('charger_control', False),
            ('charger_current', 6),
            ('relay1', False),
            ('relay2', False),
            ('surplus_freeze_until', None),
            ('actuator_battery_setpoint_w', 0.0),
            ('actuator_ev_current_a', 6),
            ('actuator_ev_enabled', False),
            ('actuator_relay1', False),
            ('actuator_relay2', False),
        )
        defaults = {}
        for key, value in default_specs:
            entity_id = self._optional_entity_id(key)
            if entity_id:
                defaults[entity_id] = value

        cfg_entity_keys = (
            'deadband_w',
            'ramp_max_w',
            'strict_limits_max_w',
            'max_battery_discharge_w',
            'max_solar_charge_w',
            'ev_min_absorb_w',
            'ev_max_absorb_w',
            'ev_charger_phases',
            'ev_force_on',
            'ev_hard_off_pv_threshold_kw',
            'ev_hard_off_low_pv_cycles',
            'ev_hard_off_release_cycles',
            'haeo_stale_timeout_s',
            'surplus_freeze_s',
            'ev_priority',
        )
        cfg_entities = {
            key: entity_id
            for key in cfg_entity_keys
            if (entity_id := self._optional_entity_id(key))
        }
        for cfg_key, value in self.cfg_overrides.items():
            entity_id = cfg_entities.get(cfg_key)
            if entity_id is not None:
                defaults[entity_id] = value
        for k, v in defaults.items():
            self.store.set_value(k, v)
            self._sync_grouped_config_entities(k, v)

        raw_net_zero_defaults = runtime_inputs_for_net_zero_intent(
            self.ent,
            rpnz_w=500.0,
            required_power_consumption_kw=0.0,
            at_s=self.now,
            pv_power_kw=3.5,
        )
        for entity_id, value in raw_net_zero_defaults.items():
            self.store.set_value(entity_id, value)
            self._sync_grouped_config_entities(entity_id, value)

        for device_id, field, value in (
            ('EV_CHARGER', 'priority', 2),
            ('EV_CHARGER', 'surplus_allowed', True),
            ('RELAY1', 'max_absorb_w', 2500),
            ('RELAY1', 'priority', 3),
            ('RELAY1', 'surplus_allowed', True),
            ('RELAY1', 'force_on', False),
            ('RELAY2', 'max_absorb_w', 5000),
            ('RELAY2', 'priority', 1),
            ('RELAY2', 'surplus_allowed', True),
            ('RELAY2', 'force_on', False),
        ):
            entity_id = self._optional_device_entity_id(device_id, field)
            if entity_id:
                self.store.set_value(entity_id, value)
                self._sync_grouped_config_entities(entity_id, value)

        if self.ent:
            seed_active_surplus_devices(self, active_device_ids=())
        # HAEO defaults / attrs
        for key in ('haeo_battery_power_active', 'haeo_ev_battery_power_active',
                    'haeo_battery_active_power_fresh_source', 'haeo_ev_active_power_fresh_source'):
            entity_id = self._optional_entity_id(key)
            if entity_id:
                self.store.set_value(entity_id, 0)
        for key in ('haeo_battery_power_active', 'haeo_ev_battery_power_active'):
            entity_id = self._optional_entity_id(key)
            if entity_id:
                self.store.set_attr(entity_id, {'forecast': []})
        self.store.set_value('input_number.ems_home_battery_ev_primary_min_absorb_w', 0)
        self.store.set_value('input_number.ems_home_battery_min_absorb_w', 0)
        self.store.set_value('input_number.ems_home_battery_default_min_absorb_w', 100)
        self.store.set_value('input_number.ems_ev_voltage_v', 230)
        self.store.set_value('sensor.ems_device_policies_pyscript', '')
        self._sync_grouped_config_entities('input_number.ems_ev_voltage_v', 230)
        for key, default in (
            ('ev_current_step_a', 4),
            ('ev_charger_phases', 1),
        ):
            entity_id = self._optional_entity_id(key)
            if entity_id:
                self._sync_grouped_config_entities(entity_id, self.store.get_value(entity_id, default))
        for device_id, field, default in (
            ('RELAY1', 'max_absorb_w', 2500),
            ('RELAY2', 'max_absorb_w', 5000),
        ):
            entity_id = self._optional_device_entity_id(device_id, field)
            if entity_id:
                self._sync_grouped_config_entities(entity_id, self.store.get_value(entity_id, default))

    def _sync_grouped_config_entities(self, entity_id, value):
        voltage_v = self.store.get_value('input_number.ems_ev_voltage_v', 230) or 230
        ev_charger_phases = self._optional_entity_id('ev_charger_phases')
        ev_current_step_a = self._optional_entity_id('ev_current_step_a')
        relay1_power_w = self._optional_device_entity_id('RELAY1', 'max_absorb_w')
        relay2_power_w = self._optional_device_entity_id('RELAY2', 'max_absorb_w')
        phases = self.store.get_value(ev_charger_phases, 1) or 1 if ev_charger_phases else 1

        if entity_id == 'input_number.ems_ev_voltage_v':
            voltage_v = value or 230
            for dep_entity_id, dep_default in (
                (ev_current_step_a, 4),
            ):
                if dep_entity_id:
                    self._sync_grouped_config_entities(dep_entity_id, self.store.get_value(dep_entity_id, dep_default))
            return

        if entity_id == ev_charger_phases:
            phases = value or 1
            for dep_entity_id, dep_default in (
                (ev_current_step_a, 4),
            ):
                if dep_entity_id:
                    self._sync_grouped_config_entities(dep_entity_id, self.store.get_value(dep_entity_id, dep_default))
            return

        if entity_id == ev_current_step_a:
            self.store.set_value('input_number.ems_ev_power_step_w', int(round(float(value) * float(phases) * float(voltage_v))))
            return

        if entity_id == relay1_power_w:
            self.store.set_value('input_number.ems_relay1_nominal_absorb_w', int(round(float(value))))
            return

        if entity_id == relay2_power_w:
            self.store.set_value('input_number.ems_relay2_nominal_absorb_w', int(round(float(value))))
            return

    def _load_module(self, file_path: Path, kind: str):
        src = file_path.read_text(encoding='utf-8')
        filtered = []
        for line in src.splitlines():
            if line.startswith('from ems_adapter.ha_adapter import'):
                continue
            filtered.append(line)
        src = '\n'.join(filtered)

        def _time_trigger(*args, **kwargs):
            def deco(fn):
                return fn
            return deco

        def _state_trigger(*args, **kwargs):
            def deco(fn):
                return fn
            return deco

        def _domain(entity_id):
            try:
                return str(entity_id).split('.', 1)[0]
            except Exception:
                return ''

        # Adapter-like API -------------------------------------------------
        def get_bool(entity_id):
            val = self.store.get_value(entity_id, False)
            if isinstance(val, str):
                return val == 'on'
            return bool(val)

        def get_float(entity_id, default=0.0):
            val = self.store.get_value(entity_id, default)
            if val in (None, 'unknown', 'unavailable', 'none', ''):
                return default
            return float(val)

        def get_int(entity_id, default=0):
            val = self.store.get_value(entity_id, default)
            if val in (None, 'unknown', 'unavailable', 'none', ''):
                return default
            return int(float(val))

        def get_str(entity_id, default=''):
            val = self.store.get_value(entity_id, default)
            if val in (None, 'unknown', 'unavailable', 'none', ''):
                return default
            return str(val)

        def age_seconds(entity_id, now_ts=None, fallback=999999.0):
            now_ts = self.now if now_ts is None else float(now_ts)
            last = self.store.last_update_ts.get(entity_id)
            if last is None:
                return fallback
            return now_ts - last

        def get_attr(entity_id, attr, default=None):
            return self.store.get_attr(entity_id, attr, default)

        def publish_sensor(entity_id, value, attrs=None):
            self.store.set_value(entity_id, value)
            self.store.set_attr(entity_id, attrs or {})

        def set_number(entity_id, value):
            domain = _domain(entity_id)
            if domain in ('input_number', 'number'):
                self.store.set_value(entity_id, value)
                return
            raise ValueError(f'unsupported numeric domain for {entity_id}')

        def set_boolean(entity_id, on):
            domain = _domain(entity_id)
            if domain in ('input_boolean', 'switch'):
                self.store.set_value(entity_id, bool(on))
                return
            raise ValueError(f'unsupported boolean domain for {entity_id}')

        def parse_input_datetime_ts(entity_id):
            raw = self.store.get_value(entity_id, None)
            if raw in (None, 'unknown', 'unavailable', 'none', ''):
                return None
            if isinstance(raw, (float, int)):
                return float(raw)
            try:
                return float(raw)
            except Exception:
                pass
            try:
                return datetime.fromisoformat(str(raw)).timestamp()
            except Exception:
                try:
                    return datetime.strptime(str(raw), '%Y-%m-%d %H:%M:%S').timestamp()
                except Exception:
                    return None

        def _set_datetime(entity_id=None, date=None, time=None, **kwargs):
            if entity_id is None:
                raise ValueError('entity_id required')
            if not date or not time:
                raise ValueError('date and time required')
            self.store.set_value(entity_id, f'{date} {time}')

        ns = {
            '__name__': f'e2e_{kind}_module',
            '__file__': str(file_path),
            'time_trigger': _time_trigger,
            'state_trigger': _state_trigger,
            'ENT': self.ent,
            'get_bool': get_bool,
            'get_float': get_float,
            'get_int': get_int,
            'get_str': get_str,
            'age_seconds': age_seconds,
            'get_attr': get_attr,
            'publish_sensor': publish_sensor,
            'set_number': set_number,
            'set_boolean': set_boolean,
            'parse_input_datetime_ts': parse_input_datetime_ts,
            'input_datetime': SimpleNamespace(set_datetime=_set_datetime),
        }
        code = compile(src, str(file_path), 'exec')
        exec(code, ns)
        return ns

    @contextmanager
    def _fake_time_module(self):
        real_time = sys.modules.get('time')
        sys.modules['time'] = SimpleNamespace(time=lambda: self.now)
        try:
            yield
        finally:
            if real_time is not None:
                sys.modules['time'] = real_time
            else:
                del sys.modules['time']

    def _run_policy_loop(self):
        with self._fake_time_module():
            self.policy_mod['ems_policy_engine_loop'](trigger_reason='e2e')

    def _run_dispatch_state_applier_loop(self):
        self.dispatch_state_applier_mod['ems_dispatch_state_applier_loop']()

    def _run_writer_loop(self):
        self.writer_mod['ems_actuator_writers_loop']()
