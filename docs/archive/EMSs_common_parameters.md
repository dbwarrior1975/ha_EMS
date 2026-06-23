# EMS common parameters and simpler entity map

Tama dokumentti arvioi kriittisesti nykyista `entity_map.py`- ja parametrimallia seka hahmottaa, milta yksinkertaisempi EMS voisi nayttaa, jos core ottaisi ohjattavat kohteet vastaan yhteismitallisina watteina.

Dokumentti on arkkitehtuurinen arvio, ei nykyisen tuotantokoodin kuvaus.

## Nykyhavainto

Nykyinen `modules/ems_adapter/entity_map.py` on littea sanakirja, jossa ovat samassa tasossa:

1. profiilit
2. yleiset EMS-parametrit
3. battery-protect-parametrit
4. EV-laturin parametrit
5. NET_ZERO floor -parametrit
6. adjustable-combo-parametrit
7. releiden parametrit
8. mittaukset
9. HAEO-ennusteet ja freshness-lahteet
10. surplus-state-latchit
11. force/allowed override -liput
12. policy-outputit
13. actuatorit

Tama toimii teknisesti, mutta arkkitehtuurisesti se tekee kolmesta asiasta vaikeaa:

1. on vaikea erottaa, mika on EMS:n domain-parametri ja mika on Home Assistant -integraatiodetalji
2. on vaikea nahda, mitka parametrit kuuluvat millekin laitteelle
3. on vaikea yleistaa akku, EV ja releet samankaltaisiksi ohjattaviksi kohteiksi

Selkein oire on akku/EV-ero:

1. akku on core-logiikassa watteina
2. EV on osin watteina, osin ampeereina
3. releet ovat tehoina kW
4. HAEO antaa tehoja kW
5. NET_ZERO ja surplus ajattelevat tehoa W/kW

Tama pakottaa core-logiikan tietamaan EV-laturin current-selectorista asioita, jotka kuuluisivat mieluummin writer-/adapter-tasolle.

## Esimerkki semanttisesta toistosta

Nykyisia akun floor-/limit-termeja:

1. `battery_protect_charge_floor_w`
2. `nz_battery_floor_default_w`
3. `nz_battery_floor_ev_active_w`
4. `max_solar_charge_w`
5. `max_battery_discharge_w`
6. `strict_limits_max_w`

Nama eivat ole kaikki samoja asioita, mutta ne muodostavat kayttajan ja kehittajan kannalta raskaan sanaston.

Kriittinen huomio:

1. osa on laitteen fyysinen raja
2. osa on guardin vaatima turvaraja
3. osa on tietyn control-polun operatiivinen floor
4. osa on yleinen EMS clamp
5. osa on roolikohtainen poikkeus, kuten EV-primary-polun battery floor

Kun kaikki ovat litteassa mapissa, nimeaminen joutuu kantamaan koko kontekstin. Siksi nimet pitenevat ja alkavat toistaa domainia: `nz_battery_floor_*`, `battery_protect_*`, `max_battery_*`.

## Tavoite: EMS ajattelee tehoa

Yksinkertaisempi tavoite olisi:

> EMS-core tekee paatokset watteina. Adapteri muuntaa watit laitekohtaisiksi ohjauksiksi.

Tama tarkoittaisi:

1. akku target: W
2. EV target: W
3. rele target/threshold: W
4. HAEO limit: W
5. surplus threshold: W
6. priority/combo: laitenimilla, ei yksikkosemantiiikalla

EV:n ampeerit eivat katoa, mutta ne siirtyvat EV-adapterin vastuulle.

Esimerkki:

```text
EMS policy:
  ev.target_w = 4600
  ev.limit_w = 5000

EV adapter:
  4600 W -> 20 A
```

Core ei silloin tarvitse tietaa, onko EV-laturin askel 1 A, 2 A vai 4 A. Core tietaa vain, paljonko tehoa EV:lle saa antaa.

## Yhteinen device-malli

Jos EMS ottaisi laitteet vastaan yhteisen mallin kautta, perusmalli voisi olla esimerkiksi:

```python
@dataclass(frozen=True)
class EmsDeviceConfig:
    id: str
    kind: str
    can_absorb_w: bool
    can_produce_w: bool
    min_absorb_w: int
    max_absorb_w: int
    max_produce_w: int
    step_w: int
    priority: int
    enabled: bool = True
```

Talla mallilla:

1. home battery on device
2. EV charger on device
3. relay1 on device
4. relay2 on device

Erot tulisivat konfiguraatiosta:

```python
home_battery = EmsDeviceConfig(
    id='HOME_BATTERY',
    kind='BATTERY',
    can_absorb_w=True,
    can_produce_w=True,
    min_absorb_w=0,
    max_absorb_w=3700,
    max_produce_w=4600,
    step_w=50,
    priority=3,
)

ev_charger = EmsDeviceConfig(
    id='EV_CHARGER',
    kind='EV_CHARGER',
    can_absorb_w=True,
    can_produce_w=False,
    min_absorb_w=920,
    max_absorb_w=6440,
    max_produce_w=0,
    step_w=920,
    priority=3,
)

relay1 = EmsDeviceConfig(
    id='RELAY1',
    kind='RELAY',
    can_absorb_w=True,
    can_produce_w=False,
    min_absorb_w=2500,
    max_absorb_w=2500,
    max_produce_w=0,
    step_w=2500,
    priority=2,
)
```

EV:n `step_w` olisi johdettu laiteadapterin parametreista:

```text
step_w = ev_current_step_a * ev_charger_phases * ev_voltage_v
```

Tama arvo voisi nakya EMS-corelle watteina, vaikka HA:ssa yha olisi `ev_current_step_a`.

## Device state

Config ei yksin riita. Core tarvitsee myos laitteiden nykytilan.

Mahdollinen yhteinen tila:

```python
@dataclass(frozen=True)
class EmsDeviceState:
    id: str
    available: bool
    active: bool
    measured_power_w: int
    current_target_w: int
    guard_state: str = 'OK'
```

Esimerkkeja:

1. akku: `current_target_w` tulee nykyisesta setpointista
2. EV: `current_target_w` johdetaan nykyisesta ampeerista
3. rele: `current_target_w` on joko `0` tai releen nimellisteho

Core nakisi kaikki tehoina. Adapteri vastaisi siita, miten HA-entityista luetaan ja mihin ne muunnetaan.

## Device policy output

Nykyinen output on laitekohtainen:

1. `policy_battery_target_w`
2. `policy_ev_current_a`
3. `policy_relay1_command`
4. `policy_relay2_command`

Yhteinen core-output voisi olla:

```python
@dataclass(frozen=True)
class DevicePolicy:
    id: str
    target_w: int
    enabled: bool
    mode: str
    reason: str
```

Esimerkit:

```text
HOME_BATTERY:
  target_w = 3000
  enabled = true
  mode = absorb

EV_CHARGER:
  target_w = 1840
  enabled = true
  mode = absorb

RELAY1:
  target_w = 0
  enabled = false
  mode = off
```

Writer/adapter muuntaisi:

1. battery `target_w` -> Victron AC power setpoint
2. EV `target_w` -> charger enable + current selector A
3. relay `enabled` -> switch on/off

## Mita entity_map voisi olla yksinkertaisimmillaan

Nykyinen entity map on yksi littea lista. Yksinkertaisempi rakenne voisi jakaa asiat ryhmiin:

```python
EMS_ENTITIES = {
    'profiles': {
        'control': 'input_select.ems_control_profile',
        'goal': 'input_select.ems_goal_profile',
        'forecast': 'input_select.ems_forecast_profile',
        'guard': 'input_select.ems_guard_profile',
    },
    'global_config': {
        'deadband_w': 'input_number.ems_deadband_w',
        'ramp_w': 'input_number.ems_ramp_max_w',
        'strict_limit_w': 'input_number.ems_strict_limits_max_w',
        'surplus_freeze_s': 'input_number.ems_surplus_freeze_s',
        'haeo_stale_timeout_s': 'input_number.ems_haeo_stale_timeout_s',
    },
    'devices': {
        'HOME_BATTERY': {
            'kind': 'BATTERY',
            'max_absorb_w': 'input_number.ems_battery_max_absorb_w',
            'max_produce_w': 'input_number.ems_battery_max_produce_w',
            'step_w': 'input_number.ems_battery_step_w',
            'target': 'number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point',
            'heartbeat': 'sensor.victron_mqtt_b827eb48c929_battery_1_battery_power',
            'soc': 'sensor.victron_mqtt_b827eb48c929_system_0_system_dc_battery_soc',
            'min_cell_voltage_v': 'sensor.victron_mqtt_b827eb48c929_battery_1_battery_min_cell_voltage',
        },
        'EV_CHARGER': {
            'kind': 'EV_CHARGER',
            'min_absorb_w': 'input_number.ems_ev_min_power_w',
            'max_absorb_w': 'input_number.ems_ev_max_power_w',
            'step_w': 'input_number.ems_ev_power_step_w',
            'enabled': 'switch.charger_control',
            'current_a': 'number.charger_current_level',
        },
        'RELAY1': {
            'kind': 'RELAY',
            'nominal_absorb_w': 'input_number.ems_relay1_power_w',
            'enabled': 'switch.relay_1_2',
        },
        'RELAY2': {
            'kind': 'RELAY',
            'nominal_absorb_w': 'input_number.ems_relay2_power_w',
            'enabled': 'switch.relay_2_2',
        },
    },
    'runtime': {
        'grid_power_w': 'sensor.average_active_power_2',
        'hourly_energy_balance_kwh': 'sensor.hourly_energy_balance',
        'required_power_w': 'sensor.required_power_consumption',
        'rpnz_w': 'sensor.ems_calculated_required_power_for_net_zero',
        'pv_power_w': 'sensor.pv_instant_power_2',
    },
    'state': {
        'surplus_freeze_until': 'input_datetime.ems_surplus_freeze_until',
        'active_devices': 'sensor.ems_active_surplus_devices',
    },
    'policy': {
        'decision_trace': 'sensor.ems_policy_decision_trace_pyscript',
        'device_policies': 'sensor.ems_device_policies_pyscript',
    },
}
```

Tassa mallissa `entity_map` ei yrita nimeta jokaista domain-saantoa omaksi avaimekseen. Se kuvaa:

1. missa profiilit ovat
2. missa yleiset EMS-parametrit ovat
3. mita laitteita EMS ohjaa
4. miten laitteet muunnetaan HA-entityihin
5. missa runtime-state ja policy-output sijaitsevat

## Mita parametreja voisi poistua tai muuttua johdetuiksi

Jos core ottaisi device-parametrit watteina, seuraavat voisivat muuttua toissijaisiksi adapter-parametreiksi tai johdetuiksi arvoiksi:

1. `ev_min_current_a`
2. `ev_max_current_a`
3. `ev_current_step_a`
4. `ev_charger_phases`

Ne eivat poistuisi EV-adapterilta, mutta core ei lukisi niita suoraan.

Core voisi nahda:

1. `ev_min_power_w`
2. `ev_max_power_w`
3. `ev_power_step_w`

Nama johdettaisiin:

```text
ev_min_power_w = ev_min_current_a * ev_charger_phases * ev_voltage_v
ev_max_power_w = ev_max_current_a * ev_charger_phases * ev_voltage_v
ev_power_step_w = ev_current_step_a * ev_charger_phases * ev_voltage_v
```

Myos releiden `relay*_power_kw` kannattaisi normalisoida watteihin:

```text
relay1_nominal_absorb_w
relay2_nominal_absorb_w
```

## Floor-termiston uudelleenarviointi

Nykyiset floor-parametrit ovat merkki siita, etta samaan domainiin on sekoittunut eri tasoja.

Parempi jako:

### Device capability

Fyysiset tai turvalliset rajat:

1. `min_absorb_w`
2. `max_absorb_w`
3. `max_produce_w`
4. `step_w`

### Guard constraint

Guardien asettamat rajat:

1. `battery_protect_min_soc`
2. `battery_protect_min_cell_voltage_v`
3. `battery_protect_min_absorb_w`

### Policy preference

NET_ZERO-polun operatiiviset mieltymykset:

1. `preferred_min_absorb_w`
2. `role_floor_w`
3. `activation_threshold_w`

Nykyinen `nz_battery_floor_ev_active_w` olisi siis ennemmin roolikohtainen policy preference kuin akun yleinen floor.

Mahdollinen uusi nimeaminen:

```text
devices.HOME_BATTERY.policy.default_min_absorb_w
devices.HOME_BATTERY.policy.ev_primary_min_absorb_w
devices.HOME_BATTERY.guard.protect_min_absorb_w
```

Tai viela yleisemmin:

```text
role_constraints.EV_PRIMARY.HOME_BATTERY.min_absorb_w
```

Kriittinen arvio: jos roolikohtaisia eroja tulee paljon, `floor`-nimitys kannattaa korvata laajemmalla `constraints`-mallilla.

## Yhteinen devices-luokka

Yksi mahdollinen seuraava domain-malli:

```python
@dataclass(frozen=True)
class EmsDevice:
    config: EmsDeviceConfig
    state: EmsDeviceState
```

EMS-core voisi muodostaa listan:

```python
devices = (
    EmsDevice(config=home_battery_config, state=home_battery_state),
    EmsDevice(config=ev_config, state=ev_state),
    EmsDevice(config=relay1_config, state=relay1_state),
    EmsDevice(config=relay2_config, state=relay2_state),
)
```

HAEO NET_ZERO -plan voisi palauttaa:

```python
primary_device_id = 'EV_CHARGER'
adjustable_device_id = 'HOME_BATTERY'
limits_w = {
    'EV_CHARGER': 5000,
    'HOME_BATTERY': 2000,
}
```

Surplus allocator voisi toimia device-listalla eika kovakoodatuilla targeteilla:

```python
SurplusTargetConfig(
    name=device.id,
    threshold_w=device.config.activation_threshold_w,
    priority=device.config.priority,
    active=device.state.active,
)
```

Tama poistaisi erillisia `relay1_priority`, `relay2_priority`, `ev_priority`, `adjustable_surplus_load_priority` -tyyppisia erikoisavaimia ja korvaisi ne device-kohtaisella `priority`-kentalla.

## Mitka erot pitaa silti sailyttaa

Yhteinen device-malli ei tarkoita, etta akku ja EV olisivat sama asia.

Akku:

1. voi absorboida tehoa
2. voi tuottaa tehoa
3. tarvitsee SOC- ja min-cell-guardit
4. on jatkuva saatoelementti
5. target voi olla negatiivinen

EV:

1. voi vain absorboida tehoa
2. tarvitsee enable/disable-kayttaytymisen
3. lopullinen ohjaus on ampeereina
4. tarvitsee minimi- ja step-rajoitteet
5. hard-off ja restore-min ovat EV-spesifeja

Relay:

1. on binaarinen on/off-kuorma
2. target on joko 0 W tai nimellisteho
3. ei tarvitse continuous ramp -mallia

Yhteinen abstraktio kannattaa rajata siihen, mika on oikeasti yhteista:

1. teho watteina
2. prioriteetti
3. aktiivisuus
4. saatavuus
5. rooli combossa
6. ylarajat ja aktivointikynnykset

Laitekohtaiset kirjoitus- ja guard-erot jaavat adapteri-/device-specific-kerrokseen.

## Milloin muutos kannattaa tehda

Muutos kannattaa tehda vasta, kun jokin naista toteutuu:

1. HAEO-combo-logiikkaa laajennetaan releisiin tai uusiin kuormiin
2. EV:n W/A-muunnos alkaa vuotaa useampaan core-moduuliin
3. `floor`-, `limit`- ja `activation`-termit alkavat saada lisaa roolikohtaisia poikkeuksia
4. `entity_map.py` kasvaa edelleen uusilla laitekohtaisilla avaimilla
5. testit alkavat kopioida samaa device-kohtaista activate/release/clamp-kaavaa

Muutos ei kannata vain kosmeettisen siivouksen takia. Hyoty syntyy vasta, jos se vahentaa oikeaa domain-monimutkaisuutta.

## Ehdotettu eteneminen

Turvallisin eteneminen olisi vaiheittainen:

1. Lisaa traceen ja sisaisiin malleihin EV:n rinnakkaiset W-arvot:
   - `ev_target_w`
   - `ev_limit_w`
   - `ev_min_power_w`
   - `ev_max_power_w`
2. Siirra EV:n A-muunnos lahemmaksi writer-/adapter-tasoa.
3. Normalisoi releiden tehot watteihin.
4. Luo `EmsDeviceConfig` vain lukumalliksi nykyisten configien paalle.
5. Luo `EmsDeviceState` vain lukumalliksi nykyisten mittausten paalle.
6. Muuta HAEO NET_ZERO -plan kayttamaan device-id + limit-w -mallia.
7. Vasta lopuksi yksinkertaista `entity_map.py` ryhmiteltyyn device-rakenteeseen.

Tarkeaa: ensimmaisessa vaiheessa ei kannata poistaa nykyisia HA-helper-entiteetteja. Ensin kannattaa tehda adapterikerros, joka muodostaa uuden device-mallin nykyisesta entity mapista. Kun testit ovat vakaat, HA-helperien nimia voi yksinkertaistaa erillisena migraationa.

## Yhteenveto

Yksinkertaisin semanttinen suunta olisi:

1. EMS-core ajattelee watteina
2. device-adapterit muuntavat watit laitekohtaisiksi ohjauksiksi
3. `entity_map.py` ryhmitellaan profiileihin, globaaleihin EMS-parametreihin, deviceihin, runtime-mittauksiin, stateen ja policy-outputteihin
4. akku, EV ja releet jaetaan yhteiseen device-malliin vain niiden aidosti yhteisten ominaisuuksien osalta
5. akku/EV/rele-erot sailyvat device-specific adaptereissa

Tama poistaisi paljon nykyista semanttista toistoa ja tekisi HAEO NET_ZERO -polun jatkokehityksesta selkeampaa. Samalla se on riittavan iso arkkitehtuurimuutos, etta se kannattaa toteuttaa adapterikerros edella eika suoraan nykyista entity mapia repimalla.
