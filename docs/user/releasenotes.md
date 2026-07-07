# Release Notes

## 2026-07-06 — Surplus candidate pool refactor

Tama release poistaa selected-single-EV / singular adjustable-surplus -rajan
NET_ZERO-coresta. `primary_device_id` sailyy singular control role -kasitteena,
mutta surplus rakennetaan nyt geneerisesta device/capability/policy-poolista.

Muutokset:

1. useampi EV voi olla samassa surplus-kandidaattipoolissa
2. kandidaatin eligibility perustuu `can_absorb_w` + `surplus_allowed` -sopimukseen
3. `priority`, `activation_threshold_w` ja `surplus_dispatch_mode` ovat device-owned
4. tuetut dispatch-modet ovat `max_absorb` ja `fixed`
5. per-device allocation tuottaa jokaiselle EV:lle oman `DevicePolicy`-tuloksen
6. non-selected EV:ta ei pakoteta `inactive_ev_policy`-tilaan vain toisen EV:n takia
7. hard-off lifecycle etenee `previous_device_states[device_id]`-tilassa itsenaisesti
8. strict-priority, EV surplus max-target, relay behavior, EV-primary stepped
   regulation, battery residual/guard, HAEO ja writer contract on sailyttetty
9. direct-v2 schema v2 validoi uudet policy-kentat tiukasti
10. generic diagnostics julkaisee candidate stackin, active device-id:t ja
    per-device surplus-targetit

Compatibility:

1. `adjustable_surplus_load` ja `adjustable_surplus_activation_w` voivat sailyä
   ulkoisina migraatiopintoina
2. `surplus_adjustable_device_id` ja `selected_ev_device_id` voivat sailyä
   diagnostiikassa, mutta ne eivat ole generic candidate execution -totuuslahde
3. `selected_ev_device_id` johdetaan deterministisesti: primary-EV ensin, muuten
   legacy EV-alias, muuten ensimmainen konfiguroitu EV
4. production `template.yaml` ei enaa johda `HOME_BATTERY`n tai `EV_CHARGER`in
   `surplus_allowed`-arvoa legacy selectorista; molemmilla on eksplisiittinen
   device-owned eligibility ja selector jaa compatibility/diagnostiikkapinnaksi

Ei kuulu scopeen: proportional multi-EV power split, EV round-robin,
strict-priority-vs-first-feasible redesign tai multi-primary control.

---

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

`runtime.*` entity-id:t ovat edelleen kayttajan konfiguroitavia read target
-pintoja. `policy_outputs` ja `diagnostics_outputs` eivat ole enaa
kayttajakonfiguraatiota, vaan kiinteita canonical output- ja
diagnostics-surfaceja koodissa.

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
