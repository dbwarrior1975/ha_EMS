# Release Notes

## 2026-07-06 — Surplus candidate pool + max_absorb threshold cleanup

Tama release poistaa selected-single-EV / singular adjustable-surplus -rajan ja
viimeistelee surplus-aktivointikynnyksen yhden totuuslahteen mallin.

Muutokset:

1. useampi EV voi olla samassa surplus-kandidaattipoolissa
2. kandidaatin eligibility perustuu `can_absorb_w + surplus_allowed` -sopimukseen
3. device-owned `priority` ja `surplus_dispatch_mode` ohjaavat jarjestysta ja target-strategiaa
4. surplus activation threshold on aina `device.capabilities.max_absorb_w`
5. erillinen `policy.activation_threshold_w` on poistettu ja vanhat paketit hylataan fail-closed
6. `adjustable_surplus_load` ja `adjustable_surplus_activation_w` on poistettu aktiivisesta global config/direct-v2 -sopimuksesta
7. dispatch diagnostics kayttaa device-ID:ita; `ADJUSTABLE`-paatosalias on poistettu
8. per-device allocation tuottaa jokaiselle EV:lle oman `DevicePolicy`-tuloksen
9. hard-off lifecycle etenee `previous_device_states[device_id]`-tilassa itsenaisesti
10. strict-priority, relay behavior, EV-primary stepped regulation, battery residual/guard, HAEO ja writer contract on sailyttetty

Compatibility:

1. `adjustable_primary_load` sailyy singular primary-role -valintana
2. `selected_ev_device_id` sailyy compatibility-diagnostiikkana, ei execution authorityna
3. kun primary ei ole EV, selected EV johdetaan korkeimmasta device-owned prioritysta eligible-EV-joukossa vakaalla tie-breakilla
4. vanhat `adjustable_surplus_load`, `adjustable_surplus_activation_w` ja device-policy `activation_threshold_w` -syotteet hylataan direct-v2:ssa eksplisiittisesti

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
