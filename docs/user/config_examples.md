# EMS config examples

Tama tiedosto kokoaa n-device-minimiesimerkit. Esimerkit nayttavat vain
olennaisen `ems.devices`- ja tarvittaessa `role_constraints`-rakenteen. Kayta
root-tason `example_EMS_config.yaml` -tiedostoa tayden grouped YAML -rakenteen
lahtopohjana ja sovita entity-id:t omaan Home Assistant -ymparistoon.

Jos esimerkkia kaytetaan `tests/e2e_entity/`-skenaarion pohjana, kopio kuuluu
skenaariokansion omaan `EMS_config.yaml`:iin. E2E-harness lukee aina
skenaariokohtaisen YAML:n, eika root-tason `EMS_config.yaml` saa toimia
testin entity registry -lahteena.

Canonical odotus kaikissa esimerkeissa:

1. `sensor.ems_device_policies_pyscript` sisaltaa device-id-kohtaiset policyt
2. `sensor.ems_surplus_dispatch_command_pyscript` sisaltaa dispatch-paatoksen
3. `sensor.ems_policy_state_pyscript` sisaltaa jatkuvuustilan
4. `sensor.ems_policy_diagnostics_pyscript` sisaltaa selityspayloadin
5. `sensor.ems_active_surplus_devices` listaa aktiiviset device-id:t
6. `sensor.ems_actuator_writer_trace` raportoi writer-toteuman `devices`-mapissa
7. vanhat yksittaiskentat tai `relay1`/`relay2`-nimet eivat ole uusi integraatiosopimus

## Only HOME_BATTERY

Kayttotarkoitus: pelkka akku ilman EV-laturia tai relekuormia.

```yaml
ems:
  role_constraints:
    HOME_BATTERY_PRIMARY: {}

  devices:
    HOME_BATTERY:
      kind: BATTERY
      capabilities:
        can_absorb_w: true
        can_produce_w: true
        min_absorb_w: input_number.ems_home_battery_min_absorb_w
        max_absorb_w: input_number.ems_max_battery_charge_w
        max_produce_w: input_number.ems_max_battery_discharge_w
        step_w: input_number.ems_deadband_w
      policy:
        priority: input_number.ems_adjustable_surplus_load_priority
        default_min_absorb_w: input_number.ems_home_battery_default_min_absorb_w
      guard:
        soc: sensor.battery_soc
        min_cell_voltage_v: sensor.battery_min_cell_voltage
        heartbeat: sensor.battery_power
        protect_soc: input_number.ems_battery_protect_soc
        protect_soc_recovery_margin: input_number.ems_battery_protect_soc_recovery_margin
        protect_min_cell_voltage_v: input_number.ems_battery_protect_min_cell_voltage_v
        protect_min_absorb_w: input_number.ems_battery_protect_charge_floor_w
      adapter:
        target_w: number.battery_power_set_point
        measured_power_w: sensor.battery_power
```

Tarvittavat helperit ovat akun capability-, guard- ja adapterientiteetit.
Lahin testattu referenssi: `tests/e2e_entity/net_zero_no_ev_relays_only/EMS_config.yaml`
poistamalla releet.

## No relay, one EV

Kayttotarkoitus: akku ja yksi EV-laturi, ei releita.

```yaml
ems:
  devices:
    HOME_BATTERY:
      kind: BATTERY
      # battery capabilities, policy, guard ja adapter

    EV_CHARGER:
      kind: EV_CHARGER
      capabilities:
        can_absorb_w: true
        can_produce_w: false
        min_absorb_w: input_number.ems_ev_min_power_w
        max_absorb_w: input_number.ems_ev_max_power_w
        step_w: input_number.ems_ev_power_step_w
      policy:
        priority: input_number.ems_surplus_ev_priority
        surplus_allowed: input_boolean.ems_ev_surplus_allowed
        low_pv_threshold_w: input_number.ems_ev_hard_off_pv_threshold_kw
        hard_off_low_pv_cycles: input_number.ems_ev_hard_off_low_pv_cycles
        hard_off_release_cycles: input_number.ems_ev_hard_off_release_cycles
      adapter:
        enabled: switch.charger_control
        current_a: number.charger_current_level
        current_step_a: input_number.ems_ev_current_step_a
        phases: input_number.ems_ev_charger_phases
        voltage_v: input_number.ems_ev_voltage_v
```

Tarvittavat helperit ovat EV:n power-, priority-, surplus_allowed-, hard_off-,
current-, current_step-, phases-, voltage- ja force_on-entityt. Testattu referenssi:
`tests/e2e_entity/net_zero_no_relays_ev_only/EMS_config.yaml`.

## No EV, relays only

Kayttotarkoitus: akku ja relekuormat ilman EV-laturia.

```yaml
ems:
  role_constraints:
    HOME_BATTERY_PRIMARY: {}

  devices:
    HOME_BATTERY:
      kind: BATTERY
      # battery capabilities, policy, guard ja adapter

    RELAY1:
      kind: RELAY
      capabilities:
        can_absorb_w: true
        can_produce_w: false
        min_absorb_w: input_number.ems_relay1_nominal_absorb_w
        max_absorb_w: input_number.ems_relay1_power_kw
        step_w: input_number.ems_relay1_power_kw
      policy:
        priority: input_number.ems_surplus_relay1_priority
        surplus_allowed: input_boolean.ems_relay1_enabled_import_zero
        force_on: input_boolean.ems_relay1_force_on
      adapter:
        enabled: switch.relay_1_2
```

Tarvittavat helperit per rele: nominal_absorb, power, priority,
surplus_allowed, force_on ja adapterin switch. Testattu referenssi:
`tests/e2e_entity/net_zero_no_ev_relays_only/EMS_config.yaml`.

## Three relays

Kayttotarkoitus: priorisoitu releketju, jossa on enemman kuin kaksi reletta.

```yaml
ems:
  devices:
    HOME_BATTERY:
      kind: BATTERY
      # battery capabilities, policy, guard ja adapter

    EV_CHARGER:
      kind: EV_CHARGER
      # EV capabilities, policy ja adapter

    RELAY1:
      kind: RELAY
      # relay 1 capabilities, policy ja adapter

    RELAY2:
      kind: RELAY
      # relay 2 capabilities, policy ja adapter

    RELAY3:
      kind: RELAY
      capabilities:
        can_absorb_w: true
        can_produce_w: false
        min_absorb_w: input_number.ems_relay3_nominal_absorb_w
        max_absorb_w: input_number.ems_relay3_power_kw
        step_w: input_number.ems_relay3_power_kw
      policy:
        priority: input_number.ems_surplus_relay3_priority
        surplus_allowed: input_boolean.ems_relay3_enabled_import_zero
        force_on: input_boolean.ems_relay3_force_on
      adapter:
        enabled: switch.relay_3_2
```

Trace-odotus: aktivointi ja vapautus nakyvat device-id:lla `RELAY3`, eivat
erillisena peilikenttana. Testattu referenssi:
`tests/e2e_entity/net_zero_priority_order_quarter_3_relays/EMS_config.yaml`.
Skenaariotestissa `RELAY3`-entityt haetaan harnessilta
`h.device_entity('RELAY3', 'enabled')`, ei paikallisesta workaround-mapista.

## Two EV chargers, one selected

Kayttotarkoitus: kaksi konfiguroitua EV-laturia, joista yksi valitaan
aktiiviseksi adjustable-laitteeksi kerrallaan.

```yaml
ems:
  global_config:
    adjustable_surplus_load: input_select.ems_adjustable_surplus_load
    adjustable_primary_load: input_select.ems_adjustable_primary_load

  role_constraints:
    HOME_BATTERY_PRIMARY:
      EV_MAIN:
        activation_threshold_w: input_number.ems_ev_main_activation_threshold_w
      EV_GARAGE:
        activation_threshold_w: input_number.ems_ev_garage_activation_threshold_w

  devices:
    HOME_BATTERY:
      kind: BATTERY
      # battery capabilities, policy, guard ja adapter

    EV_MAIN:
      kind: EV_CHARGER
      # EV_MAIN capabilities, policy ja adapter

    EV_GARAGE:
      kind: EV_CHARGER
      # EV_GARAGE capabilities, policy ja adapter
```

Valinta tapahtuu helperin arvolla, esimerkiksi `adjustable_surplus_load =
EV_MAIN`. Tama ei tarkoita multi-EV power splittia: EMS ei jaa samaa surplusia
samanaikaisesti usealle EV:lle. Testattu referenssi:
`tests/e2e_entity/net_zero_two_ev_one_relay/EMS_config.yaml`.

## Custom device IDs

Kayttotarkoitus: kuvaavat device-id:t, jotka eivat sisalla kiinteita
`RELAY1`/`RELAY2`-nimia.

```yaml
ems:
  role_constraints:
    HOME_BATTERY_PRIMARY:
      EV_MAIN:
        activation_threshold_w: input_number.ems_ev_main_activation_threshold_w
      EV_GARAGE:
        activation_threshold_w: input_number.ems_ev_garage_activation_threshold_w

  devices:
    HOME_BATTERY:
      kind: BATTERY
      # battery capabilities, policy, guard ja adapter

    EV_MAIN:
      kind: EV_CHARGER
      # EV_MAIN capabilities, policy ja adapter

    EV_GARAGE:
      kind: EV_CHARGER
      # EV_GARAGE capabilities, policy ja adapter

    RELAY_SAUNA:
      kind: RELAY
      # RELAY_SAUNA capabilities, policy ja adapter

    RELAY_BOILER:
      kind: RELAY
      # RELAY_BOILER capabilities, policy ja adapter
```

Trace-odotus: `device_policies`, `surplus_device_targets`,
`active_surplus_devices` ja writer trace kayttavat samoja device-id:ita.
Testattu referenssi:
`tests/e2e_entity/custom_device_ids_selected_single_ev/EMS_config.yaml`.
