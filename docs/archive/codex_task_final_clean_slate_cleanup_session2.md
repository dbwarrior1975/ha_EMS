# Codex Task: Final Clean-Slate Cleanup, Session 2

Paivitetty: 2026-06-29

Lahde: `codex_task_final_clean_slate_cleanup.md`

Taman dokumentin tarkoitus on antaa seuraavalle Codex-sessiolle suoraan
toteutettava vaiheistus clean-slate-loppusiivoukseen. Tavoite ei ole muuttaa
liiketoimintalogiikkaa, vaan poistaa refaktoroinnin jalkeiset aktiivisesta
arkkitehtuurista harhaanjohtavat yhteensopivuus- ja legacy-jaanteet.

## Tavoitetila

Kanoninen tuotantolinja:

```text
Grouped EMS_config.yaml
  -> CoreConfig
  -> runtime device registry
  -> device-based policy engine
  -> device_policies with target_w
  -> actuator writers
```

EV_CHARGER-politiikka on watt-native:

```text
min_absorb_w
max_absorb_w
force_on
target_w
```

EV:n ampeerit ovat sallittuja vain seuraavissa yhteyksissa:

```text
writer target_w -> current_a conversion
EV power helper tests
runtime/debug derived current fields
measured actuator state -> estimated measured power
e2e actuator output assertions
```

## Ei saa tehda

1. Ala muuta EV:n wattipohjaista semantiikkaa.
2. Ala muuta selected surplus threshold -semantiikkaa.
3. Ala muuta releiden liiketoimintasemantiikkaa.
4. Ala poista valideja EV current -apureita:

```text
ev_power_w_to_current_a
ev_current_a_to_power_w
ev_min_current_a_from_min_absorb_w
ev_max_current_a_from_max_absorb_w
```

5. Ala poista e2e actuator current -assertioita.
6. Ala poista nykyista `policy_decision_trace`- tai `device_policy`-toiminnallisuutta.
7. Ala lisaa aktiivisiin testeihin tai validaatioihin historiallisten EV-kenttien nimiin sidottuja tarkistuksia.

Historialliset EV-politiikkakentat, joita ei saa palauttaa aktiiviseen
koodiin, testeihin tai validaatiohaaroihin:

```text
adapter.current_min_a
adapter.current_max_a
adapter.force_current_a
ev_min_current_a
ev_max_current_a
ev_force_current_a
deprecated_current_min_a
deprecated_current_max_a
deprecated_force_current_a
current_min_a
current_max_a
force_current_a
```

## Vaihe 0: Aloituskartoitus

Status: todo

Tarkoitus:

Selvita nykytila ennen muutoksia ja kirjata mahdolliset valmiiksi tehdyt osat.

Toimet:

1. Aja `git status --short`.
2. Hae keskeiset jaanteet:

```bash
rg -n "surplus_dispatch_decision|ems_net_zero_surplus_dispatch_decision|policy_ev_current_a|policy_relay1_command|policy_relay2_command|policy_battery_target_w|legacy_relay_flags|relay1_on|relay2_on|charger_on|charger_current_a|current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a"
```

3. Tarkista, onko joku vaihe jo tehty osittain.
4. Kirjaa loydot tahan dokumenttiin tai erilliseen progress-osioon.

Hyvaksynta:

1. Tyopuun alkutila on tiedossa.
2. Kayttajan olemassa olevia muutoksia ei ole revertattu.
3. Jokaiselle loydetylle jaanteelle on alustava vaihe, jossa se kasitellaan.

## Vaihe 1: Poista `policy_outputs.surplus_dispatch_decision` aktiivisesta config-sopimuksesta

Status: todo

Ongelma:

`policy_outputs.surplus_dispatch_decision` nayttaa olevan vanha aktiiviseksi
jaanyt output-sopimus. Nykyinen dispatch-tieto kulkee trace-attribuuttien ja
device-policy-mekanismin kautta.

Hae:

```text
surplus_dispatch_decision
ems_net_zero_surplus_dispatch_decision
```

Tarkista ja paivita tarvittaessa:

```text
CorePolicyOutputsConfig
config validation requirements
EMS_config.yaml
example_EMS_config.yaml
tests/e2e_entity/**/EMS_config.yaml
tests/helpers.py
contract tests
aktiiviset docs-viittaukset
```

Tavoite:

1. `policy_outputs.surplus_dispatch_decision` ei ole vaadittu user config -kentta.
2. Sita ei dokumentoida aktiivisena HA policy output -entiteettina.
3. Dispatch details julkaistaan nykyisten trace-/device-policy-attribuuttien kautta.
4. Jos sisainen `outputs.surplus_dispatch_decision` on oikeasti kaytossa, se saa jaada vain sisaiseksi trace-dataksi perusteltuna.

Vaiheen testit:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/contract/test_grouped_config_contract.py
pytest -q tests/smoke/test_release_example_config_loads.py
pytest -q tests/e2e_entity/
```

Kirjaa:

```text
status:
files changed:
fields removed:
tests updated:
tests run:
remaining surplus_dispatch_decision references and justification:
```

## Vaihe 2: Poista legacy policy sensor ENT -avaimet writer-testeista

Status: todo

Ongelma:

Writer-testit eivat saa enaa kuvata vanhaa policy sensor -mallia. Niiden tulee
testata nykyista sopimusta: writer lukee `device_policies`-payloadia ja kirjoittaa
actuator-entiteetteja.

Tarkista:

```text
tests/unit/test_writer_semantics.py
```

Poista tai kirjoita uudelleen testit, joiden paaasiallinen tarkoitus on:

```text
writer ignores legacy policy sensors
device_policy wins over legacy policy sensors
writer does not fallback to legacy command/current sensors
```

Poista testiseedit:

```text
policy_battery_target_w
policy_ev_current_a
policy_relay1_command
policy_relay2_command
```

Sailyta tai kirjoita nykyista mallia kuvaaviksi:

```text
without device_policy -> writer skips
with EV device_policy target_w -> writer writes supported current_a
with RELAY device_policy target_w > 0 -> writer turns relay on
with RELAY device_policy target_w == 0 -> writer turns relay off
with BATTERY device_policy target_w -> writer writes correct battery command
mode skip/off/hard_off semantics are respected
```

Tavoite:

1. Writer-testit eivat tunne obsolete policy sensor -nimia.
2. Writer-testit validoivat vain nykyisen `device_policies`-pohjaisen kayttaytymisen.

Vaiheen testit:

```bash
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/e2e_entity/
```

Kirjaa:

```text
status:
files changed:
tests removed:
tests rewritten:
tests run:
remaining legacy policy sensor references and justification:
```

## Vaihe 3: Lisaa geneerinen strict unknown-field -validointi

Status: todo

Ongelma:

Clean-slate poisti historiallisille kentille tehdyt migraatiovirheet, mutta
grouped config ei saa silti hyvaksyya tuntemattomia tai kirjoitusvirheellisia
kenttia hiljaisesti.

Toteuta:

Lisaa geneerinen unknown-field-validointi grouped config -rakenteeseen. Virheet
eivat saa mainita historiallisia EV-kenttia erityistapauksina.

Vahintaan validoitavat polut:

```text
ems
ems.devices.<device_id>
ems.devices.<device_id>.capabilities
ems.devices.<device_id>.policy
ems.devices.<device_id>.adapter
policy_outputs
```

EV_CHARGER adapter sallii nykytilassa:

```text
enabled
current_a
current_step_a
phases
voltage_v
```

EV_CHARGER capabilities sallii:

```text
min_absorb_w
max_absorb_w
```

EV_CHARGER policy sallii:

```text
force_on
surplus_allowed
```

Tarkista RELAY- ja BATTERY-kentat nykyisesta mallista, ala paattele niita ilman
koodin lukemista.

Testit:

Lisaa neutraalit unknown-field-testit. Esimerkit:

```yaml
ems:
  devices:
    EV:
      kind: EV_CHARGER
      adapter:
        unexpected_field: input_number.foo
```

```yaml
ems:
  devices:
    RELAY1:
      kind: RELAY
      policy:
        extra_policy_flag: input_boolean.foo
```

Hyvaksyttava virhetyyli:

```text
Unknown config field: ems.devices.EV.adapter.unexpected_field
```

Tavoite:

1. Tuntemattomat kentat hylataan geneerisella schema-validoinnilla.
2. Historiallisia EV-kenttanimiä ei esiinny uusissa testeissa, aktiivisessa validaatiologiikassa tai virheviesteissa.

Vaiheen testit:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/contract/test_grouped_config_contract.py
pytest -q tests/smoke/test_release_example_config_loads.py
```

Kirjaa:

```text
status:
files changed:
validation added:
tests added:
tests run:
remaining unknown-field gaps:
```

## Vaihe 4: Poista RuntimeMeasurements scalar-riippuvuus ja `legacy_relay_flags`

Status: todo

Ongelma:

Runtime-mittaukset sisaltavat tai kayttavat viela scalar-kenttia, jotka eivat ole
device-id-native-mallin mukaisia:

```text
charger_on
charger_current_a
relay1_on
relay2_on
```

Lisaksi `device_read_model.py` sisaltaa refaktorijaanteen:

```text
legacy_relay_flags
```

Tarkista:

```text
modules/ems_core/domain/models.py
modules/ems_core/engine.py
modules/ems_core/net_zero/load_projection.py
modules/ems_adapter/device_read_model.py
modules/ems_runtime/ems_policy_engine.py
```

Tavoitemalli:

```text
RuntimeMeasurements.ev_states[device_id]
RuntimeMeasurements.relay_states[device_id]
```

Poista ensisijainen business-riippuvuus:

```text
m.charger_on
m.charger_current_a
m.relay1_on
m.relay2_on
```

Jos siirtymalogiikka tarvitsee valitun EV:n, kayta eksplisiittista rakennetta:

```text
selected_ev_device_id
selected_ev_state
```

Poista `device_read_model.py`-tiedostosta:

```text
legacy_relay_flags
```

Tavoite:

1. RuntimeMeasurements on EV- ja relay-statejen osalta device-id-native.
2. `device_read_model` ei sisalla `legacy_relay_flags`-apuria.
3. Core business logic ei riipu `relay1/relay2/charger` scalar-mittauskentista.
4. Puuttuva relay-state kasitellaan nykyisen availability/unwired-semantikan kautta.

Vaiheen testit:

```bash
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_load_projection.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/e2e_entity/
```

Kirjaa:

```text
status:
files changed:
fields removed:
functions removed:
tests rewritten:
tests run:
remaining scalar references and justification:
```

## Vaihe 5: Repository search acceptance

Status: todo

Aja ennen valmistumista:

```bash
rg -n "surplus_dispatch_decision|ems_net_zero_surplus_dispatch_decision|policy_ev_current_a|policy_relay1_command|policy_relay2_command|policy_battery_target_w|legacy_relay_flags|relay1_on|relay2_on|charger_on|charger_current_a|current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a"
```

Naiden tulee puuttua aktiivisesta koodista, testeista ja dokumentaatiosta:

```text
policy_ev_current_a
policy_relay1_command
policy_relay2_command
policy_battery_target_w
legacy_relay_flags
current_min_a
current_max_a
force_current_a
ev_min_current_a
ev_max_current_a
ev_force_current_a
deprecated_current_min_a
deprecated_current_max_a
deprecated_force_current_a
```

Naiden sallitaan jaada vain perusteltuna:

```text
surplus_dispatch_decision
relay1_on
relay2_on
charger_on
charger_current_a
```

Sallittu perustelu:

```text
internal trace/backward-compatible external IO field, not primary business logic dependency
```

Kirjaa jokainen jaava viittaus ja miksi se on sallittu.

## Lopullinen testaus

Status: todo

Aja kohdennettujen vaihetestien jalkeen:

```bash
pytest -q tests/unit/test_config_loader.py
pytest -q tests/unit/test_core_config.py
pytest -q tests/unit/test_device_read_model.py
pytest -q tests/unit/test_engine.py
pytest -q tests/unit/test_load_projection.py
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/unit/test_surplus_device_targets.py
pytest -q tests/contract/test_grouped_config_contract.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
pytest -q tests/contract/test_runtime_entity_registry_contract.py
pytest -q tests/smoke/test_release_example_config_loads.py
pytest -q tests/e2e_entity/
pytest -q
```

Lopullinen hyvaksynta:

1. `policy_outputs.surplus_dispatch_decision` ei ole vaadittu tai aktiivisesti dokumentoitu user config -output.
2. Dispatch details kulkee nykyisten trace-/device-policy-mekanismien kautta.
3. Writer-testit eivat seeda tai assertoi obsolete legacy policy sensor -avaimia.
4. Writer-testit kuvaavat vain nykyista `device_policies`-kayttaytymista.
5. Grouped configissa on geneerinen unknown-field-validointi.
6. Unknown-field-testit kayttavat neutraaleja kenttanimiä.
7. Runtime measurement -logiikka on EV- ja relay-statejen osalta device-id-native.
8. `legacy_relay_flags` on poistettu.
9. Aktiivisissa testeissa, dokumenteissa, validaatiohaaroissa tai business-logiikassa ei sailyteta historiallisia EV amp-policy -kenttia.
10. Koko testsuite menee lapi.

## Progress-malli seuraavalle sessiolle

Paivita taman dokumentin loppuun jokaisen vaiheen jalkeen:

```text
## Progress

### Phase 0: Aloituskartoitus
status: done
files changed: none
functions/fields removed: none
tests removed: none
tests rewritten: none
tests added: none
tests run: `rg -n ...`, `git status --short`
remaining searched-term references: loytyi aktiivisesta koodista `surplus_dispatch_decision`, writer-testien legacy policy sensor -seedit, `legacy_relay_flags` ja runtime scalar -riippuvuudet
allowed remaining references and justification: ei taman vaiheen jalkeen
notes: kartoitus vahvisti, etta kaikki vaiheet 1-5 olivat aidosti toteuttamatta

### Phase 1: Poista policy_outputs.surplus_dispatch_decision aktiivisesta config-sopimuksesta
status: done
files changed: `modules/ems_adapter/config_loader.py`, `modules/ems_core/domain/models.py`, `EMS_config.yaml`, `example_EMS_config.yaml`, aktiiviset `tests/e2e_entity/*/EMS_config.yaml`, `README.md`, `docs/dev/arkkitehtuuri.md`, `docs/user/EMS_parametrointi_guide.md`
functions/fields removed: `CorePolicyOutputsConfig.surplus_dispatch_decision`, grouped config required field `ems.policy_outputs.surplus_dispatch_decision`
tests removed: none
tests rewritten: fixture-configit paivitettiin uuteen policy output -sopimukseen
tests added: none
tests run: `pytest -q tests/unit/test_config_loader.py tests/contract/test_grouped_config_contract.py tests/smoke/test_release_example_config_loads.py tests/e2e_entity/`
remaining searched-term references: `surplus_dispatch_decision` jaa vain engine output -malliin ja decision trace -attribuutiksi
allowed remaining references and justification: sallittu sisaisena trace-/backward-compatible output -datana, ei enaa user config -kenttana
notes: runtime registry julkaisee dispatch-tiedon edelleen `surplus_device_dispatch_*`-attribuuteissa

### Phase 2: Poista legacy policy sensor ENT -avaimet writer-testeista
status: done
files changed: `tests/unit/test_writer_semantics.py`, `tests/e2e_entity/scenario_runner.py`, `tests/e2e_entity/e2e_conventions.md`, `docs/user/operointi.md`, `docs/user/releasenotes.md`
functions/fields removed: writer-testien legacy ENT -avaimet ja niihin sidotut seedit
tests removed: none
tests rewritten: writer-testit kirjoitettiin kuvaamaan pelkkaa `device_policies`-pohjaista kayttaytymista
tests added: none
tests run: `pytest -q tests/unit/test_writer_semantics.py tests/e2e_entity/`
remaining searched-term references: ei aktiivisessa koodissa, testeissa tai user/dev-dokumentaatiossa
allowed remaining references and justification: ei
notes: e2e helper guardrailit eivat enaa sisalla vanhoja policy sensor -nimiä

### Phase 3: Lisaa geneerinen strict unknown-field -validointi
status: done
files changed: `modules/ems_adapter/config_loader.py`, `tests/unit/test_config_loader.py`, `tests/contract/test_grouped_config_contract.py`
functions/fields removed: none
tests removed: none
tests rewritten: none
tests added: generic unknown-field testit EV adapterille, RELAY policylle ja `policy_outputs`-osiolle
tests run: `pytest -q tests/unit/test_config_loader.py tests/contract/test_grouped_config_contract.py tests/smoke/test_release_example_config_loads.py`
remaining searched-term references: ei unknown-field-validaatiossa historiallisten EV-kenttien nimia
allowed remaining references and justification: ei
notes: validointi on whitelist-pohjainen poluille `ems`, `policy_outputs`, `ems.devices.<id>`, `capabilities`, `policy`, `adapter`, ja battery `guard`

### Phase 4: Poista RuntimeMeasurements scalar-riippuvuus ja legacy_relay_flags
status: done
files changed: `modules/ems_core/domain/models.py`, `modules/ems_adapter/device_read_model.py`, `modules/ems_core/net_zero/engine.py`, `ems_policy_engine.py`, `tests/helpers.py`
functions/fields removed: `legacy_relay_flags`, `RuntimeMeasurements` scalar-kentat `charger_on`, `charger_current_a`, `relay1_on`, `relay2_on`
tests removed: none
tests rewritten: testihelper `make_m()` rakentaa nyt `ev_states`- ja `relay_states`-mapit, vaikka vanhat override-parametrit sallitaan testimigraation helpottamiseksi
tests run: `pytest -q tests/unit/test_device_read_model.py tests/unit/test_engine.py tests/contract/test_grouped_config_runtime_parity.py tests/contract/test_runtime_entity_registry_contract.py tests/e2e_entity/`
remaining searched-term references: `charger_on`, `charger_current_a`, `relay1_on`, `relay2_on` esiintyvat vain test helper -overrideina, testinimissa ja muutamassa dokumenttiselityksessa; `surplus_dispatch_decision` esiintyy sisaisessa trace-mallissa
allowed remaining references and justification: helper-overridet ovat paikallinen testikonveniessi, eivat business-logiikan syotteita; dokumenttiviittaukset kuvaavat ulkoista kytkin-/selector-kayttaytymista; `surplus_dispatch_decision` on sisainen trace-mirror
notes: core business logic ja device read model kayttavat nyt device-id-native `ev_states`- ja `relay_states`-mappeja

### Phase 5: Repository search acceptance
status: done
files changed: samat kuin vaiheissa 1-4
functions/fields removed: aktiivisesta puusta poistettu legacy policy sensor -termit, `legacy_relay_flags` ja user-config `surplus_dispatch_decision`
tests removed: none
tests rewritten: none
tests added: none
tests run: `rg -n "policy_ev_current_a|policy_relay1_command|policy_relay2_command|policy_battery_target_w|legacy_relay_flags|current_min_a|current_max_a|force_current_a|ev_min_current_a|ev_max_current_a|ev_force_current_a|deprecated_current_min_a|deprecated_current_max_a|deprecated_force_current_a" modules tests EMS_config.yaml example_EMS_config.yaml README.md docs/user docs/dev ems_policy_engine.py`
remaining searched-term references: helper-funktiot `ev_min_current_a_from_min_absorb_w` ja `ev_max_current_a_from_max_absorb_w`; sisainen `surplus_dispatch_decision`; dokumentoitu `charger_on`-kayttaytyminen; test helper -overrideparametrit `charger_on` / `charger_current_a` / `relay1_on` / `relay2_on`
allowed remaining references and justification: EV current helper -funktiot ovat ei-poistettavia domain-apureita; `surplus_dispatch_decision` on sallittu sisaisena trace-peilina; `charger_on`-viittaukset kuvaavat ulkoista actuator-tilaa eivatka runtime business-mallin primaaria rakennetta
notes: koko suite ajettiin onnistuneesti: `243 passed, 1 xfailed`
```
