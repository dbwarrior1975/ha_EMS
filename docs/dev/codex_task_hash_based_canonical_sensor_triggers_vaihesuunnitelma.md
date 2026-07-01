# Vaihesuunnitelma: canonical-sensorien counter-triggerit hash-pohjaisiksi

## Tausta

Tuotannossa dispatch_command / policy_state -refactor rollbackattiin sita
edeltavaan versioon, koska uusi toteutus aiheutti Home Assistant / Pyscript
startupissa liikaa kuormaa ja epaselvia runtime-varoituksia.

Keskeinen havainto:

```text
Counter joka policy-ajolla -> sensor state muuttuu joka ajolla
-> Pyscript state-trigger laukeaa joka ajolla
-> writer / dispatch / state-polut kaynnistyvat turhaan
-> startupissa syntyy triggerimyrsky
```

Trace-pinta oli arkkitehtuurisesti heikompi, mutta runtime-mielessa hiljaisempi:
yksi peilipinta, vahemman erillisia state-muutoksia ja vahemman downstream-
triggereita. Uuden canonical-mallin saa pitaa, mutta state-arvon taytyy muuttua
vain kun canonical payload oikeasti muuttuu.

## Tavoitetila

Kanoniset sensorit:

```text
sensor.ems_device_policies_pyscript
sensor.ems_surplus_dispatch_command_pyscript
sensor.ems_policy_state_pyscript
```

kayttavat state-arvona vakaata payload-fingerprintia:

```text
state = sha256(canonical_payload_json)[:16]
```

Varsinainen data pysyy attribuuteissa. Hash lisataan myos attribuuttiin
diagnostiikkaa varten:

```text
device_policies_hash
dispatch_command_hash
policy_state_hash
```

Tulos:

1. Ensimmainen publish voi trigata `unknown -> hash`.
2. Sama payload ei triggaa uudestaan.
3. Todellinen command/policy/state-muutos triggaa.
4. Python-globaalien counterien restart-/reload-semanttiikka poistuu.

## Tarkeat rajaukset

Ala muuta tassa tyossa:

1. EV hard_off / restore_min -semantiikkaa.
2. HAEO NET_ZERO -suunnittelulogiikkaa.
3. RPNZ release -deadbandia.
4. active_surplus_devices orderingia.
5. one-device-per-cycle dispatch -mallia.
6. Writerin idempotenssia.

Tama on runtime-triggerin stabilointityo, ei business-logiikan refactor.

## Vaihe 0: varmista lahtotila

Lue ennen toteutusta:

1. `ems_policy_engine.py`
2. `ems_actuator_writers.py`
3. `ems_dispatch_state_applier.py`
4. `modules/ems_adapter/runtime_context.py`
5. `modules/ems_adapter/config_loader.py`
6. `tests/contract/test_grouped_config_runtime_parity.py`
7. `tests/unit/test_dispatch_state_applier.py`
8. `tests/unit/test_writer_semantics.py`
9. `docs/dev/pyscript_startup_runtime_warnings_investigation.md`
10. `docs/dev/codex_task_dispatch_command_policy_state_separation_vaihesuunnitelma.md`

Huomioi, etta tyopuussa voi olla keskeneraisia muutoksia. Ala palauta niita
ilman erillista pyyntoa.

Hyvaksynta:

```bash
git status --short
pytest -q
```

Jos nykyinen branch sisaltaa jo rollbackia edeltavia hash/counter-muutoksia,
selvita ensin mitka niista kuuluvat tahan tyohon.

## Vaihe 1: lisaa vakaa canonical payload hash -helper

Luonteva paikka on `ems_policy_engine.py`, koska canonical payloadit koostetaan
siella juuri ennen publishia.

Lisaa helperit:

```python
import hashlib
import json


def _json_stable(value):
    ...


def _payload_hash(payload):
    serialized = json.dumps(_json_stable(payload), sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:16]
```

`_json_stable(...)` normalisoi ainakin:

1. dict -> avaimet stringeina, arvot rekursiivisesti.
2. list/tuple/set -> listaksi; set jarjestettyna.
3. bool/int/float/str/None sellaisenaan.
4. muu arvo -> `str(value)`.

Tavoite on, etta sama semanttinen payload tuottaa saman hashin riippumatta
tuple/list-muodosta tai dict-avainjarjestyksesta.

Testaa helper suoraan unit/contract-testissa:

1. Sama payload eri dict-jarjestyksessa tuottaa saman hashin.
2. Eri target/action tuottaa eri hashin.
3. Tuple/list normalisoituu vakaasti.

## Vaihe 2: korvaa `device_policies` counter hashilla

Nykyinen counter-malli:

```text
_DEVICE_POLICIES_VERSION += 1
publish_sensor(device_policies, version, attrs)
```

korvataan hashilla.

Hashattava canonical payload:

```python
{
    'device_policies': attrs.get('device_policies', ()),
}
```

Lisaa attribuutit:

```text
device_policies_hash
device_policies_state_kind = content_hash
```

Sailyta tarvittaessa vanha attribuutti siirtymaa varten:

```text
device_policies_version
```

mutta sen ei saa kasvaa joka ajolla. Suositus: joko poista testeista version-
odotus tai aseta se samaksi kuin hash:

```python
attrs['device_policies_hash'] = device_policies_hash
attrs['device_policies_version'] = device_policies_hash
publish_sensor(entities['device_policies'], device_policies_hash, attrs)
```

Nain nykyiset version-attribuuttia lukevat diagnostiikat eivat hajoa heti, mutta
state ei ole enaa counter.

Testit:

1. Sama device_policies payload kahdella policy-ajolla -> state pysyy samana.
2. Muutos `enabled false -> true` -> state muuttuu.
3. Muutos `target_w 0 -> 1840` -> state muuttuu.
4. Policy-listan pituus sama, sisalto muuttuu -> state muuttuu.

Luonteva paikka:

```text
tests/contract/test_grouped_config_runtime_parity.py
```

Paivita vanha testi:

```text
test_device_policies_sensor_state_is_version_not_policy_count
```

uuteen muotoon:

```text
test_device_policies_sensor_state_is_stable_content_hash
```

## Vaihe 3: julkaise `dispatch_command` hash-state

Kun dispatch_command-sensori erotetaan uudelleen tracesta, ala kayta counteria.

Hashattava canonical payload:

```python
{
    'surplus_device_dispatch_action': ...,
    'surplus_device_dispatch_decision': ...,
    'surplus_device_dispatch_device_id': ...,
    'surplus_device_dispatch_target': ...,
    'surplus_device_targets': ...,
    'surplus_freeze_until_ts': ...,
    'surplus_state_clear_reason': ...,
}
```

Jata pois hashista:

1. `dispatch_command_hash`
2. `dispatch_command_version`, jos sita pidetaan compat-attribuuttina
3. `config_cache_hit`
4. yleinen trace-/debug-data, joka ei vaikuta dispatch-stateen

Attribuutit:

```text
dispatch_command_hash
dispatch_command_state_kind = content_hash
dispatch_command_version = dispatch_command_hash  # vain compat-siirtyma, jos tarpeen
```

Testit:

1. Sama dispatch payload kahdella policy-ajolla -> state pysyy samana.
2. `NOOP -> ACTIVATE` -> state muuttuu.
3. `ACTIVATE RELAY1 -> ACTIVATE RELAY2` -> state muuttuu.
4. `surplus_freeze_until_ts` muuttuu -> state muuttuu vain jos freeze on osa
   dispatch-applierin toteutettavaa komentoa.

## Vaihe 4: julkaise `policy_state` hash-state

Hashattava canonical payload:

```python
{
    'haeo_nz_quarter_key': ...,
    'haeo_nz_primary_device_id': ...,
    'prev_force_on_device_ids': ...,
}
```

Attribuutit:

```text
policy_state_hash
policy_state_state_kind = content_hash
policy_state_version = policy_state_hash  # vain compat-siirtyma, jos tarpeen
```

Tarkeaa:

1. Ala siirra `previous_device_state`-dataa tahan sensoriin.
2. Ala hashia trace-peileja tai config-diagnostiikkaa.
3. Normalisoi `prev_force_on_device_ids` jarjestettyyn tuple/list-muotoon, jos
   sen semantiikka on joukko. Jos jarjestyksella on merkitys, sailyta jarjestys.

Testit:

1. Sama policy_state payload -> state pysyy samana.
2. `haeo_nz_quarter_key` muuttuu -> state muuttuu.
3. `haeo_nz_primary_device_id` muuttuu -> state muuttuu.
4. `prev_force_on_device_ids` muuttuu -> state muuttuu.

## Vaihe 5: tee canonical-sensorien erottelu uudelleen pienina osina

Toteutusjarjestys rollbackin jalkeen:

1. Ensin `device_policies` hash-state ja writer-trigger.
2. Sitten `dispatch_command` entity + hash-state + applier trigger.
3. Lopuksi `policy_state` entity + hash-state + policy-engine previous-state read.

Ala julkaise kaikkia uusia sensoriketjuja kerralla tuotantoon ilman valivaiheen
testausta.

Jokaisen vaiheen jalkeen:

```bash
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/unit/test_dispatch_state_applier.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/e2e_entity
```

Lopuksi:

```bash
pytest -q
```

## Vaihe 6: pidennettu startup-stabilointi

Pidetaan mukana aiemmasta tutkimuksesta opitut runtime-korjaukset:

1. `runtime_context.py` cachettaa YAML-lukemisen `path + mtime_ns + size`
   -avaimella.
2. `CoreConfig` rakennetaan edelleen joka ajolla nykyisista HA-entiteettiarvoista.
3. Tuotantopolussa ei kayteta `globals().get('read_runtime_entities')` tai
   `globals().get('read_core_config')` -kutsuja.

Staattinen testi:

```python
assert "globals().get('read_runtime_entities')" not in source
assert "globals().get('read_core_config')" not in source
```

Jos Pyscriptin `EvalFuncVarClassInst.__call__ was never awaited` jatkuu hash-
muutoksen jalkeen, seuraava tutkittava kohde on:

```text
modules/ems_adapter/ha_adapter.py
ems_dispatch_state_applier.py input_datetime.set_datetime(...)
```

Mutta hash-muutos on ensisijainen, koska se vahentaa turhat triggerit.

## Vaihe 7: tuotantorollout

Koska tuotanto on rollbackattu, deploy kannattaa tehda vaiheittain.

### Rollout A: device_policies hash

1. Vie vain device_policies hash + writer-trigger -muutos.
2. Pida dispatch edelleen trace-pohjaisena.
3. Restart Home Assistant.
4. Tarkista:

```text
sensor.ems_device_policies_pyscript state pysyy samana, jos payload ei muutu
sensor.ems_actuator_writer_trace policy_source_reason = canonical
ei toistuvia EMS_config.yaml read_text/open -varoituksia
ei triggerimyrskya startupissa
```

### Rollout B: dispatch_command hash

1. Lisaa `dispatch_command` configiin ja runtime-registryyn.
2. Julkaise dispatch_command hash-statella.
3. Vaihda dispatch-applier lukemaan canonicalia, trace fallbackina.
4. Restart Home Assistant.
5. Tarkista:

```text
sensor.ems_surplus_dispatch_command_pyscript state muuttuu vain command-muutoksessa
sensor.ems_dispatch_state_applier_trace dispatch_source_reason = canonical
trace fallback ei ole aktiivinen normaalitilassa
```

### Rollout C: policy_state hash

1. Lisaa `policy_state` configiin ja runtime-registryyn.
2. Julkaise policy_state hash-statella.
3. Vaihda HAEO/force-on previous-state read ensisijaisesti policy_stateen.
4. Restart Home Assistant.
5. Tarkista:

```text
sensor.ems_policy_state_pyscript state muuttuu vain state-payloadin muuttuessa
policy_decision_trace peilaa edelleen dashboard-kentat
previous_device_state jatkaa EV hard_off/restore_min -tilana
```

## Hyvaksyntakriteerit

1. Canonical sensorien state ei muutu, jos canonical payload ei muutu.
2. Todellinen writer/dispatch/policy-state muutos muuttaa sensor statea.
3. Startupissa ei synny jatkuvaa canonical-sensor triggeriketjua.
4. `EMS_config.yaml`-lukemista ei tehda joka loopilla.
5. Writer ja dispatch ovat edelleen idempotentteja.
6. Trace toimii edelleen diagnostiikka-/dashboard-peilina.
7. Koko testisuite menee lapi:

```text
pytest -q
```

8. Tuotannossa localtuya/discovery ei nayta karsivan EMS-triggerimyrskysta.

## Ehdotettu PR-yhteenveto

```text
Use content hashes for EMS canonical sensor states.

Replaces always-incrementing policy/dispatch/state counters with stable
canonical payload hashes so Home Assistant state triggers fire only on real
command changes. Keeps canonical sensors and trace mirrors, while reducing
startup trigger storms observed after the dispatch_command/policy_state split.
```

