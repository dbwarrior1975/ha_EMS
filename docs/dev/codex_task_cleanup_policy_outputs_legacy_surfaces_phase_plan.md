# Vaihesuunnitelma: policy outputs / legacy surfaces cleanup

Lahtodokumentti: `docs/dev/codex_task_cleanup_policy_outputs_legacy_surfaces_final.md`

Tama suunnitelma arvioi, missa jarjestyksessa cleanup kannattaa oikeasti toteuttaa nykyisen koodipuun perusteella. Tavoite on pitaa jokainen vaihe testattavana ja estaa tilanne, jossa config-validointi, runtime registry ja Pyscript-loopit rikkoutuvat kaikki samaan aikaan.

Nykytila tiivistettyna:

- `modules/ems_adapter/config_loader.py` vaatii viela `policy_outputs.decision_trace`, standalone surplus summary -kentat ja `actuator_writer_trace` saman `policy_outputs`-osion alla.
- `modules/ems_adapter/runtime_context.py` exposeeraa vanhat runtime-avaimet: `policy_decision_trace`, `surplus_*_pys` ja `actuator_writer_trace`.
- `modules/ems_core/domain/models.py` sisaltaa `CorePolicyOutputsConfig.decision_trace` ja `surplus_policy_active`.
- `ems_policy_engine.py` julkaisee edelleen `policy_decision_trace`-sensorin ja standalone surplus summary -sensorit.
- `ems_policy_engine.py` lukee `policy_state`-attribuutit ensin kanonisesta `policy_state`-sensorista, mutta fallbackaa viela `policy_decision_trace`-sensorille.
- `ems_dispatch_state_applier.py` fallbackaa `dispatch_command`-sensorista vanhaan `policy_decision_trace`-sensoriin ja kayttaa tracea myos target-resoluution fallbackina.
- `ems_actuator_writers.py` triggeroityy jo `device_policies`-sensorista, mutta lukee device policyt fallbackina vanhasta `policy_decision_trace`-sensorista.
- Testit ja e2e-skenaarioiden `EMS_config.yaml`-tiedostot nojaavat laajasti vanhoihin nimiin.

## Toteutusperiaate

Tee cleanup breaking-muutoksena, mutta vaiheista se niin, etta jokainen vaihe joko on vihrea itsessaan tai sen rikkova pinta on rajattu samaan PR/sessio-osioon.

Clean-slate-periaate:

- Ala sailyta dashboard-yhteensopivuutta, legacy-aliaksia, vanhoja entity-id:ta, deprecated config -kenttia tai fallback-lukuja diagnostiikka-/trace-payloadista.
- Jos vanha kentta esiintyy aktiivisessa configissa, validationin pitaa failata selkealla virheella.
- Jos kanoninen runtime-sensori puuttuu startupissa tai on invalidi, komponentin pitaa kayttaa eksplisiittista safe behavioria, ei fallbackata diagnostiikkaan tai vanhaan traceen.
- `policy_diagnostics` on vain selitys-/debug-pinta. Se ei saa olla command/state source.

Lopullinen aktiivinen config-muoto:

```yaml
policy_outputs:
  device_policies: sensor.ems_device_policies_pyscript
  dispatch_command: sensor.ems_surplus_dispatch_command_pyscript
  policy_state: sensor.ems_policy_state_pyscript

diagnostics_outputs:
  policy_diagnostics: sensor.ems_policy_diagnostics_pyscript
  actuator_writer_trace: sensor.ems_actuator_writer_trace
  dispatch_state_applier_trace: sensor.ems_dispatch_state_applier_trace
```

Ei saa ottaa kayttoon `legacy_dashboard_outputs`-osiota eika tukea vanhoja `policy_outputs`-aliaksia kuten `decision_trace`, `actuator_writer_trace` tai standalone surplus summary -kentat.

Tarkeimmat riippuvuudet:

1. Uusi config-sopimus ja datamallit ensin, koska muuten runtime ei voi luotettavasti tietaa uusia entity-id:ta.
2. Runtime entity registry toisena, koska writer, policy engine ja dispatch applier lukevat kaikki `ENT`-avaimia sen kautta.
3. Fallbackien poisto ennen vanhan trace-julkaisun poistoa, jotta voidaan todistaa, ettei trace ole enaa command/state-lahde.
4. Vanhojen sensorijulkaisujen poisto vasta kun testit lukevat kanonisia sensoreita.
5. Dokumentit viimeiseksi, koska niissa on paljon historiallisia viittauksia ja ne on helpointa siivota vasta toteutuneen sopimuksen mukaan.

## Vaihe 0: baseline ja rajaus

Tee ennen koodimuutoksia.

- Aja kohdennettu baseline: `pytest -q tests/unit/test_config_loader.py tests/contract/test_grouped_config_contract.py tests/contract/test_runtime_entity_registry_contract.py`
- Aja nykyiset grep-hakut ja tallenna tulokset muistiin seuraavaa vertailua varten:
  - `rg "policy_decision_trace|ems_policy_decision_trace|decision_trace" ems_*.py modules tests docs/user docs/dev`
  - `rg "policy_trace_" ems_*.py modules tests docs/user docs/dev`
  - `rg "surplus_policy_active_pys|surplus_next_target_pys|surplus_next_threshold_pys|surplus_release_candidate_pys|surplus_explanation_pys" ems_*.py modules tests docs/user docs/dev`
  - `rg "ems_net_zero_surplus_policy_active|ems_net_zero_surplus_next_target|ems_net_zero_surplus_next_threshold|ems_net_zero_surplus_release_candidate|ems_net_zero_surplus_explanation" ems_*.py modules tests docs/user docs/dev`
  - `rg "policy_source_reason|dispatch_source_reason" ems_*.py modules tests`
  - `rg "state_trigger|time_trigger" ems_*.py`

Hyvaksyntakriteeri:

- Baseline tunnetaan. Jos testit eivat ole vihreat jo ennen muutoksia, kirjaa olemassa oleva failure erikseen, ettei cleanup peita sita.

## Vaihe 1: uusi config-sopimus ja eksplisiittiset legacy-rejektiot

Toteuta ensin config loaderiin ja datamalleihin, mutta paivita samalla config-fixturet niin testit voivat kaynnistya.

Muutokset:

- Lisaa `diagnostics_outputs` sallituksi top-level EMS-osioksi.
- Muuta `policy_outputs` sallituksi vain kentille:
  - `device_policies`
  - `dispatch_command`
  - `policy_state`
- Lisaa `diagnostics_outputs` kentille:
  - `policy_diagnostics`
  - `actuator_writer_trace`
  - `dispatch_state_applier_trace`
- Paivita `CorePolicyOutputsConfig` sisaltamaan vain kanoniset runtime-outputit.
- Lisaa uusi `CoreDiagnosticsOutputsConfig` tai vastaava dataclass.
- Lisaa `CoreConfig.diagnostics_outputs`.
- Muuta validation niin vanhat kentat antavat selkean virheen, ei geneerista unknown field -viestia.
- Paivita `EMS_config.yaml`, `example_EMS_config.yaml` ja kaikki `tests/e2e_entity/**/EMS_config.yaml` uuteen muotoon.

Testit tassa vaiheessa:

- Uusi config, jossa `policy_outputs` sisaltaa vain kolme kanonista kenttaa, validoituu production-readyksi.
- Uusi `diagnostics_outputs` validoituu ja paatyy core-configiin.
- `policy_outputs.decision_trace` hylataan viestilla, joka mainitsee `diagnostics_outputs.policy_diagnostics`.
- `policy_outputs.actuator_writer_trace` hylataan viestilla, joka mainitsee `diagnostics_outputs.actuator_writer_trace`.
- `policy_outputs.dispatch_state_applier_trace` hylataan viestilla, joka mainitsee `diagnostics_outputs.dispatch_state_applier_trace`.
- Standalone surplus summary -kentat hylataan viestilla, joka sanoo sensorien poistuneen.
- `diagnostics_outputs.policy_diagnostics`, `diagnostics_outputs.actuator_writer_trace` ja `diagnostics_outputs.dispatch_state_applier_trace` hyvaksytaan.

Hyvaksyntakriteeri:

- `pytest -q tests/unit/test_config_loader.py tests/contract/test_grouped_config_contract.py tests/smoke/test_release_example_config_loads.py`
- Configissa ei ole enaa vanhoja output-kenttia aktiivisena sopimuksena.

## Vaihe 2: runtime entity registry uuteen avainmalliin

Tee vasta kun config loader osaa uuden sopimuksen.

Muutokset:

- Paivita `modules/ems_adapter/runtime_context.py` lukemaan:
  - `policy_outputs.device_policies` -> `ENT['device_policies']`
  - `policy_outputs.dispatch_command` -> `ENT['dispatch_command']`
  - `policy_outputs.policy_state` -> `ENT['policy_state']`
  - `diagnostics_outputs.policy_diagnostics` -> `ENT['policy_diagnostics']`
  - `diagnostics_outputs.actuator_writer_trace` -> `ENT['actuator_writer_trace']`
  - `diagnostics_outputs.dispatch_state_applier_trace` -> `ENT['dispatch_state_applier_trace']`
- Poista `ENT['policy_decision_trace']` ja kaikki `surplus_*_pys` registry-avaimet.
- Paivita `tests/entity_ids.py` ja runtime registry -contract testit uuteen avainjoukkoon.

Testit tassa vaiheessa:

- Registry exposeeraa kanoniset runtime-avaimet ja diagnostiikka-avaimet.
- Registry ei exposeeraa `policy_decision_trace`- tai `surplus_*_pys`-avaimia.

Hyvaksyntakriteeri:

- `pytest -q tests/contract/test_runtime_entity_registry_contract.py tests/contract/test_grouped_config_contract.py`

## Vaihe 3: poista runtime-fallbackit ennen vanhan trace-julkaisun poistoa

Tama on kriittisin arkkitehtuurivaihe. Tee ennen kuin poistat vanhan julkaistun sensorin, jotta fallbackien poisto on testattavissa erikseen.

Muutokset:

- `ems_actuator_writers.py`
  - Poista `_device_policy_source_for_id`-fallback `policy_decision_trace`-sensorille.
  - Jos `device_policies` puuttuu tai policya ei loydy, writer fail-safeaa kuten nykyinen missing policy -polku, mutta ei lue diagnostiikkaa.
  - `policy_source_reason` saa olla onnistuneella polulla vain `canonical`.
- `ems_dispatch_state_applier.py`
  - Poista fallback `policy_decision_trace`-sensorille `_read_dispatch_command`-funktiosta.
  - `_read_surplus_device_targets` lukee targetit vain `dispatch_command`-sensorista.
  - Puuttuva tai invalidi dispatch command tuottaa `NOOP`/safe behaviorin ja diagnostiikka kertoo kanonisen virheen, ei fallback-tracea.
  - Kayta `ENT['dispatch_state_applier_trace']` julkaisukohteena, ei kovakoodattua sensorinimea.
- `ems_policy_engine.py`
  - Poista `_policy_state_attr`-fallback `policy_decision_trace`-sensorille.
  - Previous-state jatkuu vain `policy_state`-sensorin attribuuteista.

Testit tassa vaiheessa:

- Writer ei lue `sensor.ems_policy_decision_trace_pyscript`-attribuutteja edes silloin kun canonical policy puuttuu.
- Dispatch applier ei lue tracea invalidin/missing dispatch commandin fallbackina.
- Policy engine previous-state lukee vain `policy_state`-sensoria.
- Writer cold start: puuttuva tai invalidi `sensor.ems_device_policies_pyscript` ei johda diagnostiikan tai vanhan trace-sensorin lukemiseen, ei kirjoita unsafe actuator targeteja, ja writer-diagnostiikka raportoi missing/invalid canonical `device_policies`.
- Dispatch cold start: puuttuva tai invalidi `sensor.ems_surplus_dispatch_command_pyscript` ei johda diagnostiikan tai vanhan trace-sensorin lukemiseen, tekee safe `NOOP`-kayttaytymisen, ja dispatch-diagnostiikka raportoi missing/invalid canonical `dispatch_command`.
- Policy engine cold start: puuttuva tai invalidi `sensor.ems_policy_state_pyscript` kayttaa tyhjia/default previous-state -arvoja, ei lue diagnostiikkaa tai vanhaa tracea, ja julkaisee tuoreen `policy_state`-outputin seuraavalla loopilla.
- Onnistuneessa loopissa:
  - `actuator_writer_trace.policy_source_reason == canonical`
  - `dispatch_state_applier_trace.dispatch_source_reason == canonical`
- Trigger-contract:
  - actuator writer state trigger osoittaa kanoniseen `sensor.ems_device_policies_pyscript`-entityyn.
  - dispatch state applier state trigger osoittaa kanoniseen `sensor.ems_surplus_dispatch_command_pyscript`-entityyn.
  - mikaan runtime `state_trigger` ei osoita `sensor.ems_policy_decision_trace_pyscript`- tai `sensor.ems_policy_diagnostics_pyscript`-entityyn command/state-kaytossa.

Hyvaksyntakriteeri:

- `pytest -q tests/unit/test_writer_semantics.py tests/unit/test_dispatch_state_applier.py tests/contract/test_grouped_config_runtime_parity.py`
- `rg "state_trigger|time_trigger" ems_*.py` tarkistettu ylla olevan trigger-contractin mukaan.
- `rg "fallback_.*decision_trace|policy_decision_trace|ems_policy_decision_trace" ems_actuator_writers.py ems_dispatch_state_applier.py ems_policy_engine.py` ei nayta aktiivisia fallbackeja.

## Vaihe 4: rename trace diagnostiikaksi ja poista standalone surplus summary -julkaisut

Tee vasta kun yksikaan runtime-polku ei tarvitse vanhaa tracea.

Muutokset:

- `ems_policy_engine.py`
  - Julkaise diagnostiikka `ENT['policy_diagnostics']`-kohteeseen.
  - Poista `entities['policy_decision_trace']`-julkaisu kokonaan.
  - Poista `surplus_policy_active_pys`, `surplus_next_target_pys`, `surplus_next_threshold_pys`, `surplus_release_candidate_pys` ja `surplus_explanation_pys` julkaisut kokonaan.
  - Lisaa diagnostiikka-attribuutit:
    - `diagnostics_contract: policy_explanation_only`
    - `runtime_contract: false`
    - `canonical_policy_output_contract: device_policies`
    - `policy_output_contract: device_policy_primary`
    - hash/version/state_kind -kentat kanonisille sensoreille tarpeen mukaan.
- Ala lisaa aktiivisia payload-kenttia nimella `policy_trace_*`.
- Nimea sisainen diagnostiikkamoduuli ja testit samassa cleanupissa, jos churn pysyy kohtuullisena:
  - `modules/ems_core/diagnostics/decision_trace.py` -> `modules/ems_core/diagnostics/policy_diagnostics.py`
  - `tests/unit/test_decision_trace.py` -> `tests/unit/test_policy_diagnostics.py`
- Jos sisainen rename osoittautuu suhteettoman isoksi, tee se erillisena saman cleanupin alavaiheena `Vaihe 4b`, ei maarittelemattomana tulevana cleanupina.
- Paivita test helperit lukemaan device policy -odotukset `sensor.ems_device_policies_pyscript`-sensorista, ei diagnostiikasta.

Testit tassa vaiheessa:

- Policy engine julkaisee `sensor.ems_policy_diagnostics_pyscript`.
- Vanhaa `sensor.ems_policy_decision_trace_pyscript`-sensoria ei julkaista.
- Standalone surplus summary -sensorit eivat synny.
- E2E/helper-assertiot lukevat `device_policies`, `dispatch_command` ja `policy_state` kanonisista sensoreista.
- Yksikaan aktiivinen payload-kentta ei ole nimeltaan `policy_trace_*`.

Hyvaksyntakriteeri:

- `pytest -q tests/unit/test_policy_diagnostics.py tests/contract/test_grouped_config_runtime_parity.py tests/e2e_entity`
- Jos rename on tehty alavaiheessa 4b vasta taman jalkeen, aja vastaava vanha/uusi testipolku tilanteen mukaan, mutta lopputilassa testin ja moduulin pitaa kayttaa `policy_diagnostics`-nimistoa.

## Vaihe 5: hash-state regression -testit ja canonical contract -vahvistus

Tee kun julkaisut ja lukupolut ovat uudessa mallissa.

Muutokset:

- Vahvista tai lisaa testit, jotka todistavat:
  - sama semantic `device_policies` payload -> sama `device_policies_hash`
  - muuttunut `device_policies` payload -> eri `device_policies_hash`
  - sama dispatch payload -> sama `dispatch_command_hash`
  - muuttunut dispatch payload -> eri `dispatch_command_hash`
  - sama policy state payload -> sama `policy_state_hash`
  - muuttunut policy state payload -> eri `policy_state_hash`
- Varmista, ettei dokumentaatio tai testinimi kuvaa hashia monotoniseksi counteriksi.

Hyvaksyntakriteeri:

- `pytest -q tests/contract/test_grouped_config_runtime_parity.py tests/unit`

## Vaihe 6: dokumentit, esimerkit ja release-note

Tee vasta kun koodi ja testit vastaavat uutta sopimusta.

Muutokset:

- Paivita `docs/dev/arkkitehtuuri.md` niin aktiivinen arkkitehtuuri nayttaa vain:
  - `policy_outputs.device_policies`
  - `policy_outputs.dispatch_command`
  - `policy_outputs.policy_state`
  - `diagnostics_outputs.policy_diagnostics`
  - `diagnostics_outputs.actuator_writer_trace`
  - `diagnostics_outputs.dispatch_state_applier_trace`
- Paivita `docs/user/EMS_parametrointi_guide.md`, `docs/user/operointi.md`, `docs/user/releasenotes.md` ja `docs/user/config_examples.md`.
- Poista aktiivisista docs/dev ja docs/user -dokumenteista `policy_decision_trace` aktiivisena sopimuksena.
- Kirjaa release noteen breaking change:
  - `policy_outputs.decision_trace` poistui.
  - standalone surplus summary -sensorit poistuivat.
  - `sensor.ems_policy_diagnostics_pyscript` korvaa vanhan selityspinnan, mutta ei ole runtime command/state source.
  - canonical sensorien state on content hash, payload attribuuteissa.
- Arkistodokumentteja `docs/archive/**` ei tarvitse siivota ellei lopullinen grep-ajokomento tarkoituksella kata archivea.

Hyvaksyntakriteeri:

- Aktiiviset docsit eivat ohjaa kayttajaa vanhoihin entityihin.
- Esimerkkiconfig on uuden sopimuksen mukainen.

## Vaihe 7: loppusiivous ja full verification

Tee lopuksi.

Komennot:

```bash
pytest -q
rg "ems_policy_decision_trace|policy_decision_trace|decision_trace" ems_*.py modules tests docs/user docs/dev
rg "policy_trace_" ems_*.py modules tests docs/user docs/dev
rg "surplus_policy_active_pys|surplus_next_target_pys|surplus_next_threshold_pys|surplus_release_candidate_pys|surplus_explanation_pys" ems_*.py modules tests docs/user docs/dev
rg "ems_net_zero_surplus_policy_active|ems_net_zero_surplus_next_target|ems_net_zero_surplus_next_threshold|ems_net_zero_surplus_release_candidate|ems_net_zero_surplus_explanation" ems_*.py modules tests docs/user docs/dev
rg "fallback_.*decision_trace|legacy_trace|fallback_deprecated_policy_diagnostics|fallback_device_policies_missing|fallback_dispatch_command" ems_*.py modules tests
rg "state_trigger|time_trigger" ems_*.py
```

Sallitut lopulliset osumat:

- Legacy-rejection testit, joissa varmistetaan vanhan configin hylkaaminen.
- Release note tai migraatioteksti, joka sanoo vanhan kentan poistuneen.
- Diagnostiikka-attribuutit kuten `surplus_explanation`, jos ne ovat tarkoituksella osa `policy_diagnostics`- tai `dispatch_command`-payloadia.
- Historialliset `docs/archive/**`-osumat, jos archive rajataan ulos aktiivisesta acceptance-grepista.

Ei sallitut osumat:

- `policy_decision_trace` writerin, dispatch-applierin tai policy enginen runtime-lukupolussa.
- `decision_trace` hyvaksyttyna config-kenttana.
- `policy_trace_*` aktiivisena payload-kenttana.
- Standalone surplus summary -sensorien julkaisu tai registry-avaimet.
- Vanha `sensor.ems_policy_decision_trace_pyscript` aktiivisissa configeissa tai docs/user-ohjeissa.
- `state_trigger` vanhaan trace-sensoriin tai `policy_diagnostics`-sensoriin runtime command/state -kaytossa.

## Suositeltu sessiojako

Jos tyota ei tehda yhdessa sessiossa, katkaise mieluummin naihin pisteisiin:

1. Sessio A: vaiheet 0-2. Lopputila: config ja registry ovat uudessa mallissa, testit vihreat valitulla rajauksella.
2. Sessio B: vaiheet 3-4. Lopputila: runtime ei lue eika julkaise vanhoja pintoja.
3. Sessio C: vaiheet 5-7. Lopputila: hash-regressiot, docsit, full `pytest -q` ja grep-acceptance.

Valtettava katkaisukohta:

- Ala lopeta sessiota tilanteeseen, jossa config loader vaatii uutta mallia mutta e2e `EMS_config.yaml`-tiedostot ovat vanhassa mallissa.
- Ala lopeta sessiota tilanteeseen, jossa vanha trace-julkaisu on poistettu mutta dispatch applier tai writer fallbackaa siihen.
- Ala lopeta sessiota tilanteeseen, jossa standalone surplus sensorit on poistettu julkaisusta mutta production readiness / registry contract viela vaatii ne.
