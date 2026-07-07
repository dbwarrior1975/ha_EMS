# EMS-operointi

## Tarkoitus

Tama dokumentti kuvaa nykyisen EMS-runtime-polun valvonnan ja perusvianetsinnan.

## Kanoninen runtime-pinta

Operoinnissa seurataan ensisijaisesti naita entiteetteja:

1. `sensor.ems_device_policies_pyscript`
2. `sensor.ems_surplus_dispatch_command_pyscript`
3. `sensor.ems_policy_state_pyscript`
4. `sensor.ems_active_surplus_devices`
5. `sensor.ems_policy_diagnostics_pyscript`
6. `sensor.ems_actuator_writer_trace`
7. `sensor.ems_dispatch_state_applier_trace`

Kaytannollinen tulkinta:

1. `device_policies` kertoo mita writerille pyydetaan
2. `dispatch_command` kertoo mita surplus-tilalle pyydetaan
3. `policy_state` kantaa yli syklien tarvittavan jatkuvuustilan
4. `active_surplus_devices` kertoo mitka surplus-kohteet ovat aktiivisia
5. `policy_diagnostics` kertoo miksi EMS paatti niin kuin paatti
6. `actuator_writer_trace` kertoo mita writer teki
7. `dispatch_state_applier_trace` kertoo miten dispatch-komento sovellettiin

## Ajastus ja diagnostiikan kuorma

Policy engine laskee paatokset `ems.policy_engine.interval_seconds`-cadencella
kiintean `2s` scheduler-tickin sisalla. `policy_diagnostics` julkaistaan
timer-ajossa heti, jos canonical output tai warning/input-quality-tila muuttuu;
muuten se julkaistaan enintaan
`ems.policy_engine.diagnostics_interval_seconds`-cadencella. Manual- ja E2E-ajot
pakottavat diagnostiikan julkaisun.

Kuormanvahennykseksi Home Assistant recorderista voi rajata diagnostiikan pois:

```yaml
recorder:
  exclude:
    entities:
      - sensor.ems_policy_diagnostics_pyscript
```

Tama ei ole correctness-vaatimus. Canonical outputit ovat
`device_policies`, `dispatch_command` ja `policy_state`.

## Hash-state semantiikka

Kolmen kanonisen output-sensorin `state` on sisaltopohjainen hash:

1. `device_policies` -> `device_policies_hash`
2. `dispatch_command` -> `dispatch_command_hash`
3. `policy_state` -> `policy_state_hash`

Varsinainen payload luetaan attribuuteista. `state` ei ole monotoninen laskuri.

## Tarkeimmat seurattavat entiteetit

### Profiilit

1. `input_select.ems_control_profile`
2. `input_select.ems_goal_profile`
3. `input_select.ems_forecast_profile`
4. `input_select.ems_guard_profile`

### Mittaukset

1. `sensor.victron_mqtt_b827eb48c929_system_0_system_dc_battery_soc`
2. `sensor.victron_mqtt_b827eb48c929_battery_1_battery_min_cell_voltage`
3. `sensor.victron_mqtt_b827eb48c929_battery_1_battery_power`
4. `sensor.average_active_power_2`
5. `sensor.hourly_energy_balance`
6. `sensor.pv_instant_power_2`

### Aktuaattorit

1. `number.victron_mqtt_b827eb48c929_system_0_system_ac_power_set_point`
2. `switch.charger_control`
3. `number.charger_current_level`
4. `switch.relay_1_2`
5. `switch.relay_2_2`

## Surplus-kandidaattipoolin valvonta

Seuraa ensisijaisesti `sensor.ems_policy_diagnostics_pyscript` -attribuutteja:

1. `surplus_candidate_device_ids`: mitka laitteet ovat poolissa
2. `surplus_candidate_stack`: strict-priority-jarjestys
3. `surplus_active_device_ids`: mitka kandidaatit ovat aktiivisia
4. `surplus_next_device_id`: seuraava activation-kohde
5. `surplus_release_device_id`: seuraava release-kohde
6. `surplus_targets_by_device_id`: per-device target/mode/active-yhteenveto
7. `device_lifecycle_states`: device-owned hard-off/lifecycle-state

Kandidaattirivista tarkista ainakin `priority`, `threshold_w`,
`threshold_source`, `surplus_dispatch_mode`, `enabled`, `force_on`, `active` ja
`activation_allowed`. `threshold_w` vastaa laitteen `capabilities.max_absorb_w`-arvoa. Kahden EV:n tapauksessa molempien device-id:iden pitaa
nakya poolissa, jos molemmilla on `can_absorb_w=true` ja
`surplus_allowed=true`.

`selected_ev_device_id` on compatibility-diagnostiikkaa. Poistetut
`adjustable_surplus_load`- ja `adjustable_surplus_activation_w`-kentat eivat kuulu
enaa aktiiviseen runtime-sopimukseen. Vianetsinnassa poolin generic kentat ja
`device_policies` ovat authoritative.

## Troubleshooting

### EMS paattaa, mutta writer ei kirjoita

1. tarkista `sensor.ems_device_policies_pyscript`
2. tarkista `sensor.ems_actuator_writer_trace`
3. tarkista laitteen `policy_source`, `reason` ja `written` writer tracesta

### Surplus-tila ei paivity odotetusti

1. tarkista `sensor.ems_surplus_dispatch_command_pyscript`
2. tarkista `sensor.ems_dispatch_state_applier_trace`
3. tarkista `sensor.ems_active_surplus_devices`
4. tarkista `input_datetime.ems_surplus_freeze_until`

### Halutaan ymmartaa policy-paatoksen syy

Tarkista ensin `sensor.ems_policy_diagnostics_pyscript` attribuutit:

1. `explanation`
2. `dominant_limitation`
3. `surplus_explanation`
4. `surplus_device_dispatch_action`
5. `surplus_device_dispatch_target`
6. `surplus_device_dispatch_device_id`
7. `surplus_device_targets`

### Invalidi tai puuttuva runtime-output

1. puuttuva tai invalidi `device_policies` johtaa writerissa safe skip -kayttaytymiseen
2. puuttuva tai invalidi `dispatch_command` johtaa dispatch-applierissa safe `NOOP` -kayttaytymiseen
3. puuttuva tai invalidi `policy_state` ei kaynnista trace-fallbackia, vaan policy engine kayttaa oletusjatkuvuutta

## Poistetut vanhat pinnat

Seuraavia ei tule enaa kayttaa dashboardeissa, automaatioissa tai templateissa:

1. vanha policy-trace-sensori
2. standalone surplus summary -sensorit
3. vanhat surplus active -boolean peilit

Jos Home Assistantissa on viela riippuvuuksia naihin, ne on paivitettava
kanonisiin `device_policies`, `dispatch_command`, `policy_state` ja
`policy_diagnostics` -pintoihin.
