# E2E refactoring guidance

Paivays: 2026-06-23

Tama dokumentti ohjaa e2e-testien paivitysta kohti nykyista EMS-sopimusta.

Nykytila 2026-06-23:

- e2e-harnessissa on canonical previous-device-state ja active-device-state -helperit
- `tests/e2e_entity` on jo pitkalla canonical device-policy/device-dispatch -mallissa
- viimeisin tarkistettu e2e-status oli `29 passed, 1 xfailed`
- xfail liittyy tarkoitukselliseen tulevaan HAEO combo-semantiikkaan, ei legacy-polun puutteeseen
- runnerissa on nyt fail-fast guardit, jotka estavat legacy behavioral assert
  -pinnan palaamisen e2e-steppeihin
- jokainen e2e-skenaario lataa oman `EMS_config.yaml`:n, ja se on testin ainoa
  config-totuus
- `QuarterScenarioHarness` rakentaa `h.ent`-registryn samasta scenario
  YAML:sta, jota runtime kayttaa
- root `tests.entity_ids.ENT` ei ole sallittu e2e-polussa, ei edes
  device-seedauksen fallbackina

## Tavoite

E2E-testien tulee todistaa nykyista tuotantoketjua:

1. policy engine julkaisee device-policyt ja device-id dispatch -tracekentat
2. dispatch state applier lukee device trace -komennon
3. writerit lukevat device-policyja
4. Home Assistant -actuatorien ja state-entityjen lopputila muuttuu odotetusti

Valittu linja on nyt tiukempi:

- e2e-testit eivat assertoi legacy policy -peileja lainkaan
- `expect_policy_values` ei kuulu enaa e2e-runneriin
- legacy policy sensorit eivat ole sallittu behavioral assert -pinta e2e-kansiossa
- testin tulee todistaa uusi device-policy/device-dispatch tuotantoketju suoraan
- harness lukee grouped-configin tiedostosta `EMS_config.yaml`
- harnessiin sidottu entity-haku tapahtuu `h.ent`- ja
  `h.device_entity(device_id, field)` -pinnan kautta

## Scenario YAML rule

`tests/e2e_entity/`-kansion jokainen skenaario on eristetty root-configista.
Kaytannossa tama tarkoittaa:

1. rakenna harness aina `scenario_dir=Path(__file__).parent` -parametrilla,
   ellei testin tarkoitus ole eksplisiittisesti root-config contract
2. hae globaalit entityt `h.ent`-registrysta
3. hae laitekohtaiset entityt `h.device_entity(device_id, field)` -helperilla
4. ala importtaa `tests.entity_ids.ENT`:a e2e-testiin, `scenario_steps.py`:hin
   tai seedaushelperiin

Jos jokin uusi skenaario tarvitsee paikallisen entity-id mapin tai root-config
lisayksen vain testia varten, rakenne on vaaralla tasolla ja se tulee korjata
scenario-YAML:iin tai harness-helperiin.

## Suosi naita assertteja

Policy trace:

- `policy_output_contract == 'device_policy_primary'`
- `device_policies`
- `surplus_device_dispatch_decision`
- `surplus_device_dispatch_action`
- `surplus_device_dispatch_target`
- `surplus_device_dispatch_device_id`
- `surplus_device_dispatch_contract == 'device_id_primary'`
- `surplus_device_next_target`
- `surplus_device_next_device_id`
- `surplus_device_release_candidate`
- `surplus_device_release_device_id`
- `haeo_nz_primary_device_id`
- `haeo_nz_adjustable_device_id`
- `haeo_nz_device_limits_w`

Dispatch state applier trace:

- `decision_source == 'device_trace'`
- `device_dispatch_action`
- `device_dispatch_target`
- `device_dispatch_device_id`
- `dispatch_state_contract == 'device_id_primary'`
- `active_surplus_device_ids`
- `writes`
- `freeze_written`

Writer trace:

- `writer_policy_contract == 'device_policy_primary'`
- per actuator branch:
  - `action`
  - `reason`
  - `written`
  - device-specific target fields, for example `target_current_a`

Device policies:

E2E runners should provide a helper that indexes `policy_trace['device_policies']` by `device_id`.

Recommended step format:

```python
'expect_device_policies': {
    'EV_CHARGER': {
        'enabled': True,
        'mode': 'burn',
        },
    'RELAY1': {
        'enabled': True,
    },
}
```

The helper should assert only the fields listed in the test step. This keeps tests readable and avoids coupling every scenario to the full device-policy payload.

## Ei enaa kayteta e2e-assertteina

Naita ei kayteta enaa e2e-kansion behavioral assert -pintana:

- `ENT['policy_ev_current_a']`
- `ENT['policy_relay1_command']`
- `ENT['policy_relay2_command']`
- `ENT['policy_battery_target_w']`
- `ENT['surplus_dispatch_decision_pys']`
- policy trace `relay1_command`
- policy trace `relay2_command`
- policy trace `surplus_dispatch_decision`

Jos naita arvoja testataan lainkaan, se kuuluu contract- tai compatibility-testiin, ei `tests/e2e_entity/`-kansioon.

## Fully device-native target

Jos kansio halutaan siivota myos viimeisesta compatibility-kerroksesta, taman lisaehdon tulee toteutua nykyisen canonical-mallin paalle:

- `expect_dispatch_state` ei nojaa kenttiin
  - `adjustable_active`
  - `relay1_active`
  - `relay2_active`
  vaan kayttaa ensisijaisesti:
  - `active_surplus_device_ids`
  - `device_dispatch_action`
  - `device_dispatch_target`
  - `device_dispatch_device_id`

- `expect_values` ei nojaa ensisijaisesti kenttiin
  - `ENT['surplus_r1_active']`
  - `ENT['surplus_adjustable_active']`
  - `ENT['surplus_r2_active']`
  ellei testin tarkoitus ole erikseen todistaa HA-visible state peilia

- skenaarion setup ei perustu actuator- tai active-state peilien lavastamiseen, jos sama aiempi tila voidaan kuvata canonical helperilla tai device-level seedilla

- kansio ei tarvitse folder-kohtaista writer-trace, dispatch-state tai freeze-helper poikkeuslogiikkaa

- testi ei nojaa EV:n sisaisiin cadence-/mooditrace-kenttiin kuten `ev_policy_mode`, jos sama kayttaytyminen voidaan todistaa `device_policies`, dispatch-tracella ja actuator-lopputilalla

- jos testi tarkistaa actuator-entityja, niiden rooli on loppuvaikutuksen todentaminen, ei policy- tai dispatch-semantiiikan ensisijainen totuuslahde

Kaytannossa taman tason siivous tarkoittaa, etta testin paalogiikka luetaan trace/device-policy -pinnasta ja HA-entityt jaavat vain lopputilan varmistukseksi.

## Fully legacy-free e2e target

Canonical device-policy -malli poistaa legacy-pinnat testien odotusarvoista. Fully legacy-free -taso menee pidemmalle: e2e-testit, runnerit ja harness eivat enaa tarvitse legacy policy -sensoreita, legacy surplus-active -entityja tai niiden attribuutteja edes aiemman syklin tilan seedaamiseen.

Taman tason tavoite on:

1. Testit kuvaavat inputin grouped device configina, HA-mittauksina ja canonical runtime seedina.
2. Policy engine julkaisee vain device-policy/device-dispatch -sopimuksen mukaiset testattavat arvot.
3. Dispatch state applier yllapitaa aktiiviset device-id:t canonical state -mallissa.
4. Writerit lukevat device-policyja ja kirjoittavat HA-actuatorit.
5. HA-visible actuatorit todentavat lopputuloksen, mutta eivat toimi policy- tai dispatch-semantiiikan lahteena.

Fully legacy-free -mallissa seuraavat eivat saa esiintya `tests/e2e_entity/`-testien, runnerien tai scenario setupin tarvitsemana tietona:

- `ENT['policy_ev_current_a']`
- `ENT['policy_relay1_command']`
- `ENT['policy_relay2_command']`
- `ENT['policy_battery_target_w']`
- `ENT['surplus_dispatch_decision_pys']`
- `ENT['surplus_r1_active']`
- `ENT['surplus_adjustable_active']`
- `ENT['surplus_r2_active']`
- `ev_policy_mode` legacy-attribuuttina
- `policy_source`
- dispatch-state booleanit `adjustable_active`, `relay1_active`, `relay2_active`

Poikkeus: dokumentaatiossa termit saavat esiintya vain historiallisena selityksena tai poistettavien rajapintojen listana.

## Fully legacy-free migration plan

Taysin legacy-vapaaseen e2e-malliin siirtyminen kannattaa tehda kahdessa kerroksessa: ensin runtimeen canonical state -rajapinta, sitten e2e-harnessin siivous. Muuten testit joutuvat edelleen kirjoittamaan vanhoja entityja, vaikka niiden assertit olisivat jo oikein.

### 1. Maarittele canonical previous-cycle state

Luo runtimeen yksi canonical rakenne aiemman syklin muistille. Sen tulee korvata EV:n nykyinen riippuvuus `policy_ev_current_a`-attribuuteista.

Tarvittavat tiedot:

- device-id, esimerkiksi `EV_CHARGER`
- viimeisin device mode, esimerkiksi `burn`, `restore_min`, `hard_off`
- low-PV cadence counter tai vastaava hard-off/recovery -tilakoneen tila
- viimeisin kirjoitettu device-policy niilta osin kuin seuraava sykli tarvitsee sita

E2E-helperin tavoitemuoto:

```python
seed_previous_device_state(
    h,
    device_id='EV_CHARGER',
    mode='hard_off',
    low_pv_cycles=2,
)
```

Tama helper ei saa kirjoittaa `ENT['policy_ev_current_a']`-attribuutteja.

### 2. Maarittele canonical surplus runtime state

Korvaa `surplus_r1_active`, `surplus_adjustable_active` ja `surplus_r2_active` canonical device-id -pohjaisella aktiivisten laitteiden tilalla.

Tavoitemuoto:

```python
seed_active_surplus_devices(
    h,
    active_device_ids=['EV_CHARGER', 'RELAY2'],
)
```

Runtime lukee taman jatkossa canonical state -lahteesta ja dispatch-state trace raportoi saman arvon kentassa `active_surplus_device_ids`.

### 3. Paivita runtime lukemaan canonical state ensin

Policy engine, dispatch state applier ja writerien tarvitsema aiemman tilan luku tulee vaihtaa canonical state -rajapintaan.

Siirtymasaanto:

- uusi canonical state on ensisijainen
- legacy fallback voidaan sallia vain erillisissa compatibility-testeissa
- e2e-harness ei saa kayttaa fallbackia

Kun grouped config on oletus ja legacy fallback on poistumassa, e2e-polun tulee olla tiukempi kuin tuotannon mahdollinen lyhytaikainen compatibility-polku.

### 4. Siivoa e2e helperit

Kun runtime ei tarvitse vanhoja entityja, poista tai nimea uudelleen seuraavat helperit:

- `seed_previous_ev_policy_state`
- `seed_surplus_runtime_state`

Korvaavat helperit:

- `seed_previous_device_state`
- `seed_active_surplus_devices`

Uudet helperit saavat kirjoittaa vain canonical test state -pintaan. Jos ne joutuvat edelleen kirjoittamaan legacy entityja, migraatio ei ole valmis.

### 5. Siivoa scenario setupit

Poista `scenario_steps.py`-tiedostoista setup-rivit, jotka alustavat:

- `ENT['surplus_r1_active']`
- `ENT['surplus_adjustable_active']`
- `ENT['surplus_r2_active']`

Korvaa ne tarvittaessa canonical helperilla, joka kuvaa aktiiviset device-id:t.

### 6. Kirista e2e-runnerin guardit

Lisae e2e-runneriin fail-fast tarkistus, joka kaataa testin jos stepissa, odotusarvoissa tai helperin julkisessa APIssa kaytetaan legacy-pintaa.

Guardin tulee estaa ainakin:

- `expect_policy_values`
- `policy_source`
- `ev_policy_mode`
- `adjustable_active`
- `relay1_active`
- `relay2_active`
- `ENT['policy_*']`
- `ENT['surplus_*_active']`

Tama tekee regressiosta nakyvan heti eika vasta dokumenttikatselmoinnissa.

### 7. Siirra legacy-compatibility erilliseen testialueeseen

Jos vanhojen entityjen yhteensopivuutta halutaan viela todistaa, se ei kuulu `tests/e2e_entity/`-kansioon.

Suositeltu jako:

- `tests/e2e_entity/`: vain canonical, fully legacy-free
- `tests/compatibility/` tai vastaava: legacy input/output fallbackit, jos niita viela pidetaan tuotannossa

Nain e2e-testit kertovat uuden arkkitehtuurin totuuden, eika niihin jaa vanhaa mallia vahingossa elamaan.

### 8. Valmis-kriteeri

Fully legacy-free -tila on saavutettu, kun seuraava haku ei palauta osumia `tests/e2e_entity/`-kansiosta lukuun ottamatta tata dokumenttia ja historiallisia suunnitelmadokumentteja:

```bash
rg -n "expect_policy_values|policy_ev_current_a|policy_battery_target_w|policy_relay1_command|policy_relay2_command|surplus_dispatch_decision_pys|policy_source|adjustable_active|relay1_active|relay2_active|surplus_r1_active|surplus_adjustable_active|surplus_r2_active|ev_policy_mode" tests/e2e_entity
```

Lisaksi koko e2e-suite menee lapi:

```bash
python3 -m pytest -q tests/e2e_entity
```

## Mika saa edelleen olla canonical-siirtymavaiheen e2e-assertti

Actuator and state entity outputs are still valuable e2e assertions:

- `ENT['actuator_battery_setpoint_w']`
- `ENT['actuator_ev_enabled']`
- `ENT['actuator_ev_current_a']`
- `ENT['actuator_relay1']`
- `ENT['actuator_relay2']`
- `ENT['surplus_r1_active']`
- `ENT['surplus_adjustable_active']`
- `ENT['surplus_r2_active']`
- `ENT['surplus_freeze_until']`

These are not policy-source assertions. They prove that the whole production chain produced the correct Home Assistant-visible result.

Huomio: fully legacy-free -tavoitetasolla `surplus_*_active` ei enaa kuulu `tests/e2e_entity/`-kansion assert-pintaan. Silloin aktiivinen surplus-tila todennetaan canonical device-id -kentasta `active_surplus_device_ids`, ja HA-visible lopputila rajataan varsinaisiin actuator-entityihin seka mahdollisiin uusiin canonical state -entityihin.

## Valittu migration pattern

Kun vanha e2e-kansio paivitetaan:

1. Update the folder's `scenario_steps.py` first.
2. Point the folder harness to `project_root / 'EMS_config.yaml'`.
3. Add `expect_device_policies` support.
4. Remove automatic legacy policy mirror checks from the runner.
5. Replace `expect_policy_values` with `expect_device_policies`.
6. Replace legacy dispatch assertions with canonical `surplus_device_dispatch_*` fields.
7. Add dispatch applier assertions for `decision_source`, `device_dispatch_*` and `dispatch_state_contract`.
8. Add writer branch assertions for action/reason/written and device-specific target fields.
9. Keep actuator/state `expect_values` assertions.
10. If a scenario needs previous-cycle seed state during the canonical transition, hide any temporary compatibility writes behind a helper so the test file itself stays on the canonical model.
11. Run the folder tests.
12. Run the full suite before finishing.

Jos tavoitteena on myos fully device-native -taso:

13. Replace `adjustable_active` / `relay1_active` / `relay2_active` checks with `active_surplus_device_ids`.
14. Remove active-state booleans from the folder's primary behavioral assertions.
15. Reduce actuator assertions to end-state verification only.

Jos tavoitteena on fully legacy-free -taso:

16. Replace compatibility seed helpers with canonical previous-device-state and active-device-state helpers.
17. Remove all `ENT['policy_*']` and `ENT['surplus_*_active']` writes from `tests/e2e_entity/`.
18. Add fail-fast guards that reject legacy fields in e2e steps and helper APIs.
19. Move any remaining legacy fallback verification to compatibility tests outside `tests/e2e_entity/`.

## Example

Before:

```python
'expect_policy': {
    'surplus_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
},
'expect_policy_values': {
    ENT['policy_ev_current_a']: 28,
    ENT['policy_relay1_command']: 1,
},
```

After:

```python
'expect_policy': {
    'surplus_device_dispatch_decision': 'ACTIVATE_ADJUSTABLE',
    'surplus_device_dispatch_action': 'ACTIVATE',
    'surplus_device_dispatch_target': 'ADJUSTABLE',
    'surplus_device_dispatch_device_id': 'EV_CHARGER',
    'surplus_device_dispatch_contract': 'device_id_primary',
},
'expect_device_policies': {
    'EV_CHARGER': {
        'enabled': True,
        'mode': 'burn',
        },
    'RELAY1': {
        'enabled': True,
    },
},
'expect_dispatch_state': {
    'decision_source': 'device_trace',
    'device_dispatch_action': 'ACTIVATE',
    'device_dispatch_target': 'ADJUSTABLE',
    'device_dispatch_device_id': 'EV_CHARGER',
    'dispatch_state_contract': 'device_id_primary',
},
```

## Release note for tests

E2E tests should now answer this question:

"Did the current device-id/device-policy production contract produce the expected Home Assistant-visible state?"

They should not primarily answer:

"Did the old legacy policy sensor contain the old migration value?"

## Refactored folders

Seuraavat alikansiot on siivottu taman dokumentin mukaiseen canonical device-policy e2e -malliin:

- `battery_protect_min_cell_recovery`
- `goal_transition_net_zero_to_max_export`
- `haeo_01_cheap_grid_charge_fresh_forecast`
- `haeo_02_net_zero_homebattery_primary_ev_adjustable`
- `hard_off_on_low_pv`
- `net_zero_ev_adjustable_load`
- `net_zero_force_on_battery_support`
- `net_zero_homebattery_adjustable_load`
- `net_zero_priority_order_quarter`
- `optimizer_degraded_fallback`
- `system_degraded_safe_mode`

Huomio: osa skenaarioista tarvitsee edelleen aiemman syklin tilan seedauksen helperin kautta, koska runtime lukee kyseista tilaa viela compatibility-attribuuteista. Tama on kapseloitu helperiin, eika se ole sallittu e2e-testien oma assert- tai step-rakenne.

Lisahuomio: `goal_transition_net_zero_to_max_export` on taman hetken puhtain referenssikansio. Se ei enaa assertoi legacy policy -peileja, dispatch-state booleaneja, EV:n sisaisia `ev_policy_mode`-traceja tai writer-branchien `policy_source`-kenttaa. Jelle jaavat actuator-entityt ovat tarkoituksella vain lopputilan e2e-varmistus.
