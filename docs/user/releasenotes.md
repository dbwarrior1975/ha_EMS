# Release Notes

Paivays: 2026-07-01

## Scope

Tama release viimeistelee policy output -siivouksen:

1. grouped `EMS_config.yaml` on kanoninen konfiguraatio
2. runtime-outputit ovat `device_policies`, `dispatch_command` ja `policy_state`
3. diagnostiikka-outputit ovat `policy_diagnostics`, `actuator_writer_trace` ja `dispatch_state_applier_trace`
4. writer ja dispatch-applier eivat fallbackaa vanhoihin trace-sensoreihin

## Breaking changes

Seuraavat poistuvat aktiivisesta sopimuksesta:

1. `policy_outputs.decision_trace`
2. `policy_outputs.actuator_writer_trace`
3. `policy_outputs.dispatch_state_applier_trace`
4. standalone surplus summary -sensorit
5. vanha `sensor.ems_policy_decision_trace_pyscript`

Jos Home Assistant -automaatiot, dashboardit tai template-sensorit ovat
nojaaneet naihin, ne on paivitettava.

## Canonical outputs

Kayta jatkossa ensisijaisesti naita:

1. `sensor.ems_device_policies_pyscript`
2. `sensor.ems_surplus_dispatch_command_pyscript`
3. `sensor.ems_policy_state_pyscript`
4. `sensor.ems_policy_diagnostics_pyscript`
5. `sensor.ems_active_surplus_devices`
6. `sensor.ems_actuator_writer_trace`
7. `sensor.ems_dispatch_state_applier_trace`
8. `input_datetime.ems_surplus_freeze_until`

## Hash-state contract

Kanonisten output-sensorien `state` on sisaltopohjainen hash:

1. `device_policies` -> `device_policies_hash`
2. `dispatch_command` -> `dispatch_command_hash`
3. `policy_state` -> `policy_state_hash`

Payload luetaan attribuuteista. `state` ei ole counter eika versionumero
monotonisessa merkityksessa.

## Configuration

Kanoninen konfiguraatiomuoto on:

```yaml
ems:
  policy_outputs:
    device_policies: sensor.ems_device_policies_pyscript
    dispatch_command: sensor.ems_surplus_dispatch_command_pyscript
    policy_state: sensor.ems_policy_state_pyscript

  diagnostics_outputs:
    policy_diagnostics: sensor.ems_policy_diagnostics_pyscript
    actuator_writer_trace: sensor.ems_actuator_writer_trace
    dispatch_state_applier_trace: sensor.ems_dispatch_state_applier_trace
```

## Upgrade note for HA users

Paivita mahdolliset automaatiot ja dashboardit pois vanhoista policy-trace- ja
surplus-summary-entiteeteista. Suositeltu uusi tarkastelupinta on:

1. `sensor.ems_policy_diagnostics_pyscript`
2. `sensor.ems_device_policies_pyscript`
3. `sensor.ems_surplus_dispatch_command_pyscript`
4. `sensor.ems_policy_state_pyscript`
5. `sensor.ems_active_surplus_devices`
6. `sensor.ems_actuator_writer_trace`
7. `sensor.ems_dispatch_state_applier_trace`
