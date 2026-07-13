# Validoidut esimerkit

Tämän dokumentin YAML-lohkot ovat lyhyitä rakenneotteita. Täydelliset, testisuitessa parsitut tiedostot ovat paketissa.

## Mitä tiedostoa käytetään mihinkin

| Tiedosto | Käyttö |
|---|---|
| `EMS_config.yaml` | productionin staattinen runtime v5 -topologia |
| `template.yaml` | täydellinen `template:`-osio runtime-sensoreineen |
| `examples/template_include.example.yaml` | sama sisältö `template: !include` -fragmenttina |
| `examples/EMS_config.static.example.yaml` | kommentoitu kopio staattisesta topologiasta |
| `example_EMS_config.yaml` | kehitys-/E2E-harnessin täydellinen grouped-config, ei productionin ensisijainen input |
| `example_EMS_runtime_packet_sensors.yaml` | rajattu runtime-sensorien contract-esimerkki |

## Suositeltu beta-topologia

```text
primary order: EV_CHARGER → HOME_BATTERY
producer pool: HOME_BATTERY
surplus pool: EV_CHARGER, HOME_BATTERY, RELAY1, RELAY2
```

Tällä mallilla:

```text
request 900 W
EV minimum 1840 W → EV skip
HOME_BATTERY → effective primary

request 2500 W
EV available → EV effective primary
HOME_BATTERY voi edelleen olla producer muilla tickeillä
```

## Staattinen `EMS_config.yaml`

Production-tiedostossa määritellään vain topologia ja roolit:

```yaml
ems:
  runtime_sources:
    policy_config:
      entity_id: sensor.ems_policy_config_runtime
    measurements:
      entity_id: sensor.ems_measurements_runtime
    policy_state:
      entity_id: sensor.ems_policy_state_runtime
  policy_engine:
    interval_seconds: 5
    diagnostics_interval_seconds: 30
  devices:
    HOME_BATTERY:
      kind: BATTERY
      capabilities:
        can_absorb_w: true
        can_produce_w: true
        supports_primary_consuming_regulation: true
        supports_producing_regulation: true
```

Täydellinen tiedosto: `EMS_config.yaml`.

## Runtime policy config

Strict policy-paketissa pitää olla myös global-configin kaikki pakolliset arvot. Älä rakenna omaa pakettia lyhyestä dokumenttilohkosta. Käytä `template.yaml`:n `EMS Policy Config Runtime` -sensorin rakennetta.

Tärkeitä global-kenttiä:

```text
deadband_w
ramp_w
strict_limit_w
default_sp_w
surplus_freeze_s
battery_heartbeat_timeout_s
haeo_stale_timeout_s
nz_battery_floor_default_w
nz_battery_floor_ev_active_w
primary_consuming_device_ids
```

## Entity registry

Template sisältää geneeriset mappingit:

```yaml
entity_registry:
  state:
    surplus_freeze_until: input_datetime.ems_surplus_freeze_until
    active_surplus_devices: sensor.ems_active_surplus_devices
  devices:
    HOME_BATTERY:
      target_w: number.ems_home_battery_target_w
    EV_CHARGER:
      enabled: switch.ems_ev_charger_enabled
      current_a: number.ems_ev_charger_current_a
    RELAY1:
      enabled: switch.ems_relay1_enabled
```

Korvaa ne omilla entity-ID:illä. Puuttuva pakollinen actuator-mapping failaa suljetusti.

## Include-muoto

Koko osio:

```yaml
template:
  - sensor:
```

`template: !include` -fragmentti:

```yaml
- sensor:
```

Molemmat esimerkit generoidaan samasta template-sisällöstä ja parsitaan release-auditissa.

## Esimerkkien validointi

Release-portit tarkistavat:

- YAML-parsinnan
- runtime schema v5:n
- kaikki pakolliset relay producer-defaultit
- primary-listan contractin
- runtime-templateattribuuttien Jinja-string-muodon
- grouped-configin latauksen ja smoke-ajon

Esimerkki on turvallinen lähtökohta vasta sen jälkeen, kun kaikki geneeriset entity-ID:t on korvattu oman järjestelmän arvoilla.
