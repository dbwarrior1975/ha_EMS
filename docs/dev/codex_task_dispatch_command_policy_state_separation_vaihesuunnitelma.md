# Vaihesuunnitelma: dispatch-command ja policy-state irti policy_decision_trace-sensorista

## Arvio alkuperaisesta ehdotuksesta

Luettu dokumentti: `codex_task_separate_dispatch_command_and_policy_state_from_trace.md`.

Ehdotus on toteuttamiskelpoinen muutettuna. Nykyinen koodi vahvistaa keskeisen ongelman:

1. `ems_dispatch_state_applier.py` triggeroityy yha `sensor.ems_policy_decision_trace_pyscript`-sensorista.
2. Dispatch-applier lukee komennon `policy_decision_trace`-attribuuteista.
3. `ems_policy_engine.py` lukee HAEO NET_ZERO -jatkuvuuden ja force-on edge -tilan `policy_decision_trace`-attribuuteista.
4. `device_policies` on jo erotettu omaksi versionoiduksi writer-sopimuksekseen, joten sama malli sopii dispatch-commandille ja policy-statelle.

Ehdotusta ei kannata toteuttaa aivan sellaisenaan, vaan vaiheistaa ja tarkentaa nain:

1. Ensin lisataan uudet entityt konfiguraatioon ja runtime entity -rakentajaan. Muuten policy-engine ja dispatch-applier joutuvat kayttamaan kovakoodattuja fallbackeja liian pitkalle.
2. Dispatch-command kannattaa erottaa omaksi pieneksi sopimukseksi ennen policy-statea. Se on rajattu muutos ja siihen on jo selkea applier-testipinta.
3. Uusi `policy_state` saa sisaltaa HAEO/force-on -tilan, mutta ei `previous_device_state`-sensorin nykyista EV hard_off/restore_min -tilaa. `previous_device_state` on jo oma state-sensorinsa ja kuuluu jattaa paikalleen.
4. `policy_decision_trace` saa edelleen peilata kentat dashboardeja ja nykyisia e2e-assertioita varten, mutta mikaan uusi kanoninen lukupolku ei saa ensisijaisesti riippua tracesta.
5. Trace-fallback on perusteltu ensimmaisessa tuotantokelpoisessa vaiheessa, mutta sen kayton pitaa nakya diagnostisissa attribuuteissa.

## Tavoitetila

Kanoniset pinnat:

```text
sensor.ems_device_policies_pyscript
  -> actuator writer

sensor.ems_surplus_dispatch_command_pyscript
  -> dispatch state applier

sensor.ems_policy_state_pyscript
  -> policy engine previous-state input

sensor.ems_policy_decision_trace_pyscript
  -> diagnostics/dashboard mirror
```

Nykyinen `sensor.ems_previous_device_state` jatkaa EV-kohtaisen hard_off/restore_min -jatkuvuuden kanonisena tilana.

## Vaihe 0: varmistus ennen koodimuutoksia

Lue viela ennen toteutusta:

1. `ems_policy_engine.py`
2. `ems_dispatch_state_applier.py`
3. `modules/ems_adapter/runtime_context.py`
4. `modules/ems_adapter/config_loader.py`
5. `modules/ems_core/domain/models.py`
6. `tests/unit/test_dispatch_state_applier.py`
7. `tests/contract/test_grouped_config_runtime_parity.py`
8. `tests/e2e_entity/scenario_harness.py`

Huomioi, etta tyopuussa voi olla keskeneraisia muutoksia. Ala palauta niita.

## Vaihe 1: lisaa entity-sopimus konfiguraatioon

Muokattavat tiedostot:

1. `EMS_config.yaml`
2. kaikki `tests/e2e_entity/*/EMS_config.yaml` -skenaariokonfigit
3. `modules/ems_adapter/config_loader.py`
4. `modules/ems_adapter/runtime_context.py`
5. `modules/ems_core/domain/models.py`
6. `tests/entity_ids.py` tarvittaessa vain epasuorasti, koska se lukee configin
7. `tests/contract/test_runtime_entity_registry_contract.py`
8. `tests/unit/test_config_loader.py`
9. `tests/unit/test_core_config.py`

Lisaavat policy output -avaimet:

```yaml
policy_outputs:
  dispatch_command: sensor.ems_surplus_dispatch_command_pyscript
  policy_state: sensor.ems_policy_state_pyscript
```

Tee naista pakolliset kentat grouped config -validoinnissa. Paivita myos:

1. `ALLOWED_POLICY_OUTPUT_KEYS`
2. `_validate_required_entities(...)`
3. `build_runtime_entities_from_grouped_config(...)`
4. `CorePolicyOutputsConfig`
5. `build_core_config_from_grouped_reader(...)`

Poista tai muuta vanha warning:

```text
runtime still publishes device policies primarily via decision_trace attrs
```

Se ei enaa kuvaa nykytilaa, koska writer lukee kanonisesti `device_policies`-sensoria.

Hyvaksynta vaiheelle:

```bash
pytest -q tests/unit/test_config_loader.py tests/unit/test_core_config.py tests/contract/test_runtime_entity_registry_contract.py
```

## Vaihe 2: julkaise versionoitu dispatch_command policy-enginesta

Muokattava tiedosto: `ems_policy_engine.py`.

Lisaa module-level counter samaan tyyliin kuin `_DEVICE_POLICIES_VERSION`:

```python
_DISPATCH_COMMAND_VERSION = 0
```

Julkaise uusi sensor juuri policy-outputtien laskennan jalkeen ja ennen tracea. Ensimmainen toteutus saa kasvattaa version joka policy-ajolla. Applierin taytyy olla idempotentti, joten tama on turvallinen ja yksinkertainen.

Dispatch-command attrs kannattaa koostaa samoista `attrs`-kentista, jotta kenttanimet eivat muutu:

```text
dispatch_command_version
surplus_device_dispatch_action
surplus_device_dispatch_decision
surplus_device_dispatch_device_id
surplus_device_dispatch_target
surplus_device_targets
surplus_freeze_until_ts
surplus_state_clear_reason
surplus_explanation
```

Pidä `policy_decision_trace`-mirror ennallaan tassa vaiheessa.

Lisaattavat testit:

1. `dispatch_command`-sensorin state vastaa `dispatch_command_version`-attribuuttia.
2. State muuttuu kahden policy-ajon valissa.
3. Attribuuteissa on ainakin action, target/device_id ja freeze.

Luonteva paikka on `tests/contract/test_grouped_config_runtime_parity.py`, koska siella on jo vastaava `device_policies`-version testaus.

## Vaihe 3: siirra dispatch-applier lukemaan dispatch_commandia

Muokattava tiedosto: `ems_dispatch_state_applier.py`.

Muuta state-trigger:

```python
@state_trigger('sensor.ems_surplus_dispatch_command_pyscript')
```

Pida periodinen 30 sekunnin trigger varalla.

Muuta `_read_dispatch_command()` lukemaan ensin:

```text
entities['dispatch_command']
```

Fallback saa lukea `entities['policy_decision_trace']`, mutta vain jos dispatch-command puuttuu tai sen action ei ole validi. Fallbackin pitaa palauttaa nakyvat diagnostiikat.

Suositeltu palautusrakenne:

```python
{
    'source_entity': dispatch_entity,
    'source_reason': 'canonical',
    'version': dispatch_command_version,
    'action': action,
    'target': target,
    'device_id': resolved_device_id,
    'decision_name': decision_name,
    'decision': decision,
}
```

Traceen lisattavat attribuutit:

```text
decision_source = dispatch_command
dispatch_source_entity
dispatch_source_reason
dispatch_command_version
```

Jos fallback kaytettiin:

```text
dispatch_source_reason = fallback_dispatch_command_missing
```

Paivita `tests/unit/test_dispatch_state_applier.py`:

1. Trigger-contract testi: state trigger sisaltaa `sensor.ems_surplus_dispatch_command_pyscript` eika sisalla `sensor.ems_policy_decision_trace_pyscript`.
2. Canonical voittaa trace-ristiriidan.
3. Trace fallback toimii, jos canonical puuttuu.
4. Nykyiset trace-lahteiset testit muutetaan canonical-lahteisiksi tai nimetaan fallback-testeiksi.

## Vaihe 4: julkaise versionoitu policy_state policy-enginesta

Muokattava tiedosto: `ems_policy_engine.py`.

Lisaa counter:

```python
_POLICY_STATE_VERSION = 0
```

Julkaise `entities['policy_state']` jokaisella policy-ajolla.

Ensimmainen policy-state payload:

```text
policy_state_version
haeo_nz_quarter_key
haeo_nz_primary_device_id
prev_force_on_device_ids
```

Ala siirra naita kenttia pois `policy_decision_trace`-attribuuteista viela. Ne saavat jaada mirroriksi.

Tarkeaa: ala siirra `previous_device_state`-dataa tahan uuteen sensoriin tassa muutoksessa. Se on jo oma state-sensorinsa ja sita kaytetaan EV hard_off/restore_min -jatkuvuuteen.

Testit:

1. `policy_state`-sensorin state vastaa `policy_state_version`-attribuuttia.
2. Sensorilla on HAEO- ja force-on-kentat.
3. Trace mirror sisaltaa yha samat kentat nykyisten dashboardien ja testien takia.

## Vaihe 5: vaihda policy-enginen previous-state-luku policy_stateen

Muokattava tiedosto: `ems_policy_engine.py`.

Korvaa ensisijaiset lukupolut:

```python
get_attr(entities['policy_decision_trace'], 'haeo_nz_quarter_key', '')
get_attr(entities['policy_decision_trace'], 'haeo_nz_primary_device_id', '')
get_attr(entities['policy_decision_trace'], 'prev_force_on_device_ids', ())
```

uudella lukupolulla:

```python
get_attr(entities['policy_state'], 'haeo_nz_quarter_key', '')
get_attr(entities['policy_state'], 'haeo_nz_primary_device_id', '')
get_attr(entities['policy_state'], 'prev_force_on_device_ids', ())
```

Tee helper, joka lukee ensin `policy_state` ja fallbackaa traceen vain jos canonical-entity puuttuu tai attribuutti puuttuu.

Suositeltavat helperit:

```python
def _policy_state_attr(entities, key, default):
    ...

def _read_previous_force_on_device_ids(entities):
    ...
```

Lisaattavat testit:

1. Kun `policy_state` ja trace ovat ristiriidassa, policy engine kayttaa `policy_state`-arvoa.
2. Sama erikseen kentille `haeo_nz_quarter_key`, `haeo_nz_primary_device_id` ja `prev_force_on_device_ids`.
3. Trace fallback toimii vain canonical policy_state -puutostilanteessa.

## Vaihe 6: paivita dokumentaatio ja e2e-apurit

Muokattavat tiedostot tarpeen mukaan:

1. `docs/dev/arkkitehtuuri.md`
2. `docs/dev/ems_step_model.md`
3. `docs/dev/e2e_tests_stories.md`
4. `tests/e2e_entity/scenario_runner.py`
5. `tests/e2e_entity/scenario_harness.py`

Paivita teksti niin, etta:

1. `policy_decision_trace` on diagnostiikka.
2. `device_policies` on writerin kanoninen sopimus.
3. `dispatch_command` on dispatch-applierin kanoninen sopimus.
4. `policy_state` on HAEO/force-on previous-state -kanoninen sopimus.
5. `previous_device_state` on yha EV previous-state -kanoninen sopimus.

E2E-apurit voivat edelleen lukea odotuksia tracesta, jos ne tarkistavat diagnostiikkaa. Jos ne tarkistavat kanonista dispatchia tai statea, lue jatkossa uusilta sensoreilta.

## Vaihe 7: regressiotestit

Aja ensin kohdennetut testit:

```bash
pytest -q tests/unit/test_dispatch_state_applier.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/unit/test_config_loader.py tests/unit/test_core_config.py
```

Aja sitten ainakin nama e2e-skenaariot:

```bash
pytest -q tests/e2e_entity/net_zero_priority_order_quarter/
pytest -q tests/e2e_entity/net_zero_priority_order_quarter_3_relays/
pytest -q tests/e2e_entity/net_zero_force_on_battery_support/
pytest -q tests/e2e_entity/hard_off_on_low_pv/
pytest -q tests/e2e_entity/net_zero_ev_adjustable_load/
pytest -q tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable/
```

Lopuksi:

```bash
pytest -q
```

## Riskit ja rajaukset

1. Version kasvattaminen joka policy-ajolla lisaa dispatch-applierin ajoja. Se on hyvaksyttavaa, koska applierin state-muutokset ovat idempotentteja. Jos trace-melu kasvaa liikaa, optimoi myohemmin sisaltohashilla.
2. Fallback traceen voi peittaa virheita. Siksi fallbackin pitaa nakya `dispatch_state_applier_trace`-diagnostiikassa.
3. Kaikkien e2e `EMS_config.yaml` -tiedostojen paivitys on helppo unohtaa. Kayta `rg "policy_outputs:" tests/e2e_entity -n`.
4. Ala muuta EV watt-native -mallia, RPNZ-deadbandia, active surplus -jarjestysta, force-on-semanttiikkaa tai yhden laitteen per sykli -mallia.
5. Ala poista `policy_decision_trace`-mirror-kenttia samassa PR:ssa.

## Valmis kun

1. `sensor.ems_surplus_dispatch_command_pyscript` on konfiguroitu ja julkaistu versionoidulla state-arvolla.
2. Dispatch-applier triggeroityy dispatch-command-sensorista ja lukee sen ensisijaisesti.
3. Trace-ristiriitatilanteessa canonical dispatch-command voittaa.
4. `sensor.ems_policy_state_pyscript` on konfiguroitu ja julkaistu versionoidulla state-arvolla.
5. Policy engine lukee HAEO/force-on previous-state -arvot ensisijaisesti `policy_state`-sensorilta.
6. `previous_device_state` jatkaa EV previous-state -sensorina.
7. `policy_decision_trace` toimii diagnostiikkapeilina, ei kanonisena command/state-lahteena.
8. Kohdennetut testit ja full suite menevat lapi.

## Ehdotettu PR-kuvaus

```text
Separate dispatch command and persistent policy state from policy_decision_trace.

Adds versioned dispatch_command and policy_state sensors, moves dispatch_state_applier
to the dispatch_command trigger/input, and moves HAEO/force-on previous-state reads to
policy_state. policy_decision_trace remains as a diagnostic mirror for dashboards and
existing observability.
```
