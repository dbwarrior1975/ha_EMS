from __future__ import annotations

import copy
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from ems_adapter.entity_map import ENT


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
    Entity-map-level quarter simulator for the current three-loop production chain:

        policy loop -> internal surplus latch loop -> writer loop

    This harness intentionally exercises the library the same way production does now:
    - dispatcher decisions are written by ems_net_zero_shadow.py
    - ems_surplus_latches.py converts dispatch decisions to active latches/freeze state
    - ems_actuator_writers.py consumes policy outputs and updates actuator/shadow entities
    """

    def __init__(self, project_root: Path, start_ts: float = 0.0, step_s: int = 30):
        self.project_root = Path(project_root)
        self.store = FakeEntityStore()
        self.now = float(start_ts)
        self.step_s = int(step_s)
        self.history = []

        self.policy_mod = self._load_module(self.project_root / 'ems_net_zero_shadow.py', kind='policy')
        self.latch_mod = self._load_module(self.project_root / 'ems_surplus_latches.py', kind='latch')
        self.writer_mod = self._load_module(self.project_root / 'ems_actuator_writers.py', kind='writer')
        self._seed_defaults()

    def set_entities(self, mapping: dict):
        self.store.set_now(self.now)
        for entity_id, value in mapping.items():
            self.store.set_value(entity_id, value)

    def set_attrs(self, entity_id: str, attrs: dict):
        self.store.set_now(self.now)
        self.store.set_attr(entity_id, attrs)

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

    def step(self, set_values: dict | None = None, note: str = ''):
        self.store.set_now(self.now)
        if set_values:
            self.set_entities(set_values)

        self._run_policy_loop()
        self._run_latch_loop()
        self._run_writer_loop()

        snap = self.snapshot(note=note)
        self.history.append(snap)
        self.now += self.step_s
        self.store.set_now(self.now)
        return snap

    def _seed_defaults(self):
        self.store.set_now(self.now)
        defaults = {
            ENT['control_profile']: 'AUTOMATIC',
            ENT['goal_profile']: 'NET_ZERO',
            ENT['forecast_profile']: 'NONE',
            ENT['guard_profile']: 'NORMAL_LIMITS',
            ENT['battery_protect_soc']: 2,
            ENT['battery_protect_soc_recovery_margin']: 1,
            ENT['battery_protect_min_cell_voltage_v']: 3.03,
            ENT['deadband_w']: 50,
            ENT['ramp_max_w']: 1000,
            ENT['strict_limits_max_w']: 4600,
            ENT['max_solar_charge_w']: 3700,
            ENT['ev_min_current_a']: 4,
            ENT['ev_max_current_a']: 28,
            ENT['ev_charger_phases']: 1,
            ENT['ev_force_current_a']: 0,
            ENT['haeo_stale_timeout_s']: 300,
            ENT['relay1_power_kw']: 2.5,
            ENT['relay2_power_kw']: 5.0,
            ENT['relay1_priority']: 3,
            ENT['relay2_priority']: 1,
            ENT['ev_priority']: 2,
            ENT['soc']: 50.0,
            ENT['min_cell_voltage_v']: 3.20,
            ENT['victron_heartbeat']: 0.0,
            ENT['grid_power_w']: 0.0,
            ENT['current_battery_sp']: 100.0,
            ENT['hourly_energy_balance']: 0.0,
            ENT['charger_control']: False,
            ENT['charger_current']: 4,
            ENT['relay1']: False,
            ENT['relay2']: False,
            ENT['required_power_consumption_kw']: 0.0,
            ENT['rpnz_w']: 500.0,
            ENT['surplus_freeze_until']: None,
            ENT['surplus_ev_active']: False,
            ENT['surplus_r1_active']: False,
            ENT['surplus_r2_active']: False,
            ENT['relay1_enabled_import_zero']: True,
            ENT['relay2_enabled_import_zero']: True,
            ENT['relay1_force_on']: False,
            ENT['relay2_force_on']: False,
            ENT['actuator_victron_setpoint_w']: 0.0,
            ENT['actuator_ev_current_a']: 4,
            ENT['actuator_ev_enabled']: False,
            ENT['actuator_relay1']: False,
            ENT['actuator_relay2']: False,
        }
        for k, v in defaults.items():
            self.store.set_value(k, v)

        # HAEO defaults / attrs
        self.store.set_value(ENT['haeo_battery_power_active'], 0)
        self.store.set_value(ENT['haeo_ev_battery_power_active'], 0)
        self.store.set_value(ENT['haeo_battery_active_power_fresh_source'], 0)
        self.store.set_value(ENT['haeo_ev_active_power_fresh_source'], 0)
        self.store.set_attr(ENT['haeo_battery_power_active'], {'forecast': []})
        self.store.set_attr(ENT['haeo_ev_battery_power_active'], {'forecast': []})

    def _load_module(self, file_path: Path, kind: str):
        src = file_path.read_text(encoding='utf-8')
        filtered = []
        for line in src.splitlines():
            if line.startswith('from ems_adapter.entity_map import'):
                continue
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
            'time_trigger': _time_trigger,
            'state_trigger': _state_trigger,
            'ENT': ENT,
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
        exec(src, ns)
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
            self.policy_mod['ems_net_zero_shadow_loop']()

    def _run_latch_loop(self):
        self.latch_mod['ems_surplus_latches_loop']()

    def _run_writer_loop(self):
        self.writer_mod['ems_actuator_writers_loop']()
