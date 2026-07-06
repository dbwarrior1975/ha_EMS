# Release Notes

## 2026-07-06 - Capability-driven NET_ZERO refactor

### Scope

Tama release siirtaa NET_ZERO:n keskisen execution-spinen EV/BATTERY-role-
kytkennasta device/capability-driven-malliin.

Keskeiset muutokset:

1. uudet pakolliset capabilityt `supports_primary_regulation` ja `supports_residual_regulation`
2. `uses_hard_off_lifecycle` sailyy erillisena lifecycle-capabilityna
3. sisaiset roolit normalisoidaan `primary_device_id` / `surplus_adjustable_device_id`
4. residual-regulaattori johdetaan capabilitysta
5. geneerinen primary-target kayttaa min/max/step power envelopea
6. hard-off release-counter koskee lifecycle-devicea role-independentisti
7. device-owned `previous_device_states[device_id]` on authoritative lifecycle-store
8. canonical `DevicePolicy`-output ja nykyinen actuator contract sailyvat

### Configuration upgrade

Jokaisella schema-v2 devicella tulee olla eksplisiittisesti:

```yaml
capabilities:
  uses_hard_off_lifecycle: true|false
  supports_primary_regulation: true|false
  supports_residual_regulation: true|false
```

Direct-v2 validoi nama strict booleaneina. String `"true"` tai numerot `0`/`1`
eivat kelpaa.

Oletussemantiikka nykyisille laitteille:

1. HOME_BATTERY: primary `true`, residual `true`
2. EV_CHARGER: primary `true`, residual `false`
3. RELAY: primary `false`, residual `false`

### Role validation

1. eksplisiittisesti sama primary- ja surplus-device hylataan
2. primaryn on tuettava primary-regulaatiota
3. combosta on loydyttava residual-regulaattori
4. invalidia yhdistelmaa ei korjata hiljaisella EV/BATTERY cross-combo fallbackilla

### Hard-off bug fix

Korjattu production-roolissa `HOME_BATTERY primary / EV adjustable` havaittu bugi,
jossa yksittainen RPC-kynnyksen ylitys saattoi vapauttaa hard-offin ennen
`hard_off_release_cycles`-countia.

Nyt:

1. recovery-condition kasvattaa counteria perakkaisilla kierroksilla
2. katkeava recovery nollaa counterin
3. release tapahtuu vasta required-countissa
4. sama count-sopimus koskee primary- ja surplus-adjustable-roolia

### Compatibility

Seuraavat voivat sailyä diagnostiikan compatibility-kenttina:

1. `selected_ev_device_id`
2. `ev_policy_mode`
3. `ev_hard_off_active`
4. `ev_hard_off_release_ready_cycles`
5. `previous_ev_device_states`

Geneeriset authoritative-kentat ovat muun muassa:

1. `primary_device_id`
2. `surplus_adjustable_device_id`
3. `residual_regulator_device_id`
4. `previous_device_states`
5. `device_lifecycle_states`

### Validation

Varmennettu toimitus-ZIPista purettuna:

- full suite: `468 passed, 0 failed, 1 xfailed`
- baseline ennen refactoria: `446 passed, 0 failed, 1 xfailed`
- uusia failure-ID:ita: ei yhtaan

---

## 2026-07-01 - Canonical policy output cleanup

### Scope

Tama release viimeisteli policy output -siivouksen:

1. grouped `EMS_config.yaml` on kanoninen konfiguraatio
2. runtime-outputit ovat `device_policies`, `dispatch_command` ja `policy_state`
3. diagnostiikka-outputit ovat `policy_diagnostics`, `actuator_writer_trace` ja `dispatch_state_applier_trace`
4. writer ja dispatch-applier eivat fallbackaa vanhoihin trace-sensoreihin

### Breaking changes

Seuraavat poistuivat aktiivisesta sopimuksesta:

1. `policy_outputs.decision_trace`
2. `policy_outputs.actuator_writer_trace`
3. `policy_outputs.dispatch_state_applier_trace`
4. standalone surplus summary -sensorit
5. vanha `sensor.ems_policy_decision_trace_pyscript`

### Canonical outputs

Kayta ensisijaisesti:

1. `sensor.ems_device_policies_pyscript`
2. `sensor.ems_surplus_dispatch_command_pyscript`
3. `sensor.ems_policy_state_pyscript`
4. `sensor.ems_policy_diagnostics_pyscript`
5. `sensor.ems_active_surplus_devices`
6. `sensor.ems_actuator_writer_trace`
7. `sensor.ems_dispatch_state_applier_trace`
8. `input_datetime.ems_surplus_freeze_until`

### Monotonic version -state contract

Canonical output -sensorien `state` on muutoksesta eteneva versionumero:

1. `device_policies` -> `device_policies_version`
2. `dispatch_command` -> `dispatch_command_version`
3. `policy_state` -> `policy_state_version`

Versionumero etenee vain kyseisen canonical payloadin muuttuessa. Payload luetaan
attribuuteista.
