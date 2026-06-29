# N-Device Surplus Handoff

Paivitetty: 2026-06-22

## Tarkoitus

Tama on handoff seuraavaa sessiota varten. Tavoite on vieda surplus-kuormien
refaktorointi loppuun siihen alkuperaiseen tavoitetilaan, jossa EMS tukee:

1. `0-n` `kind: RELAY` -laitteita
2. `0-n` `kind: EV_CHARGER` -laitteita
3. edelleen vain yhta `HOME_BATTERY`-akkua
4. device-id -pohjaista dispatchia, writeria, tracea ja e2e-harnessia ilman
   kiinteita `RELAY1` / `RELAY2` / `EV_CHARGER` oletuksia tuotantopolussa

Lue ensin myos:

1. [surplusloads_to_support_more_flexibiity.md](/home/virtamik/code/ha_EMS/docs/archive/surplusloads_to_support_more_flexibiity.md)
2. [legacy_free_release_handoff.md](/home/virtamik/code/ha_EMS/docs/archive/legacy_free_release_handoff.md)
   vain taustakontekstina legacy-release cleanupista. Se ei ole enaa
   authoritative n-device suunnitelma, ja osa sen nykytila-/testiajo-
   havainnoista on vanhentunut tassa tyopuussa tehtyjen myohempien muutosten
   jalkeen.

## Tamanhetkinen tilanne

Nykyinen toteutus on osittain generinen, mutta ei viela paasta paahan
n-releinen tai n-EV-yhteensopiva.

Vahvistettu toimiva osa:

1. `CoreConfig.devices` registry voi kantaa ylimaaraisia deviceja.
2. `build_core_config_from_grouped_reader(...)` sailyttaa ainakin `RELAY3`-
   tyyppisen ylimaaraisen relay-devicen `core.devices`-mapissa.
3. `device_read_model` lukee CoreConfigin deviceja registrysta ja tunnistaa
   ylimaaraiset releet, jos runtime-state annetaan device-id -mapissa.
4. `build_surplus_device_targets(...)` ottaa relay-candidate-listan eika ole
   enaa rakenteellisesti rajattu kahteen releeseen.
5. `ems_actuator_writers_loop()` iteroi `cfg.devices` ja kutsuu relay-writeria
   kaikille `kind == 'RELAY'` -deviceille.

Tunnettu puuttuva osa:

1. Runtime-entity alias -kerros rakentaa edelleen top-level avaimet vain
   `relay1_*` ja `relay2_*`.
2. `tests.entity_ids.ENT` ei saa avainta `actuator_relay3`, vaikka
   `entities['devices']['RELAY3']` voi olla olemassa.
3. `seed_active_surplus_devices(...)` jarjestaa ja seedaa vain
   `RELAY1`, `EV_CHARGER`, `HOME_BATTERY`, `RELAY2`.
4. `ems_dispatch_state_applier.py` sisaltaa edelleen fixed-id -logiikkaa
   `RELAY1`, `RELAY2`, `EV_CHARGER`, `HOME_BATTERY`.
5. `ems_policy_engine.py` sisaltaa edelleen compatibility-polkuja, jotka lukevat
   `relay1_*` ja `relay2_*` arvoja.
6. Usean EV:n tuki on registry-tasolla osittainen, mutta EV primary/surplus,
   previous-state, hard-off ja writer-semantics tarvitsevat viela eksplisiittisen
   n-EV-validoinnin.

## Miksi uusi 3 releen e2e kaatuu

Uusi testi:

- `tests/e2e_entity/net_zero_priority_order_quarter_3_relays/test_01_activation_chain.py`

Kaatuminen:

```text
KeyError: 'actuator_relay3'
```

Syy:

1. Testi kayttaa `ENT['actuator_relay3']`.
2. `ENT` rakennetaan tiedostossa `tests/entity_ids.py` kutsumalla
   `build_runtime_entities_from_grouped_config(...)`.
3. `modules/ems_adapter/runtime_context.py` luo nykyisin litteat compatibility-
   aliakset vain `actuator_relay1` ja `actuator_relay2`.
4. Sama runtime-context keraa kuitenkin jo `relay_device_ids` ja rakentaa
   device-kohtaisen `entities['devices']` registryn.

Johtopaatos: kyse ei ole vain testivirheesta. Se paljastaa, etta n-device
tuki ei viela ole paasta paahan valmis.

Tarkea huomio testin nykytilasta:

Uusi 3 releen e2e-skenaario on kopioitu 2 releen skenaariosta, joten sen
step-odotukset eivat viela ole luotettava kuva 3 releen tavoitesemantiikasta.
Kun KeyError ja harness-polku on korjattu, testin odotukset taytyy kayda
uudelleen lapi nykyisen policy/dispatch-kayttaytymisen perusteella.

Erityisesti tarkistettavia kohtia:

1. activation order, kun mukana ovat `RELAY1`, `EV_CHARGER`, `RELAY2`,
   `RELAY3`
2. jokaisen stepin `surplus_device_dispatch_decision`
3. `surplus_device_next_target` ja `surplus_device_next_device_id`
4. `surplus_explanation`-tekstit, koska ne voivat kayttaa canonical device-id:ta
   tai compatibility decision-namea tilanteesta riippuen
5. `expect_device_policies` kaikille neljalle surplus-deviceille
6. `expect_dispatch_state.active_surplus_device_ids` aktivointi- ja release-
   jarjestyksen mukaan
7. actuator-odotukset, koska uusi testi ei saa olettaa `actuator_relay3`
   top-level aliasia

## Tarkea korjaus suunnitelmaan

`surplusloads_to_support_more_flexibiity.md` merkitsee useita vaiheita
`completed`-tilaan, mutta nykyinen koodi ei viela tayta kaikkia niiden
hyvaksyntakriteereja n-laitteille.

Erityisesti:

1. Vaihe 4 "Runtime entity registry" on vain osittain valmis.
   Device-registry on olemassa, mutta top-level aliasit ja testiharness ovat
   edelleen kahden releen oletuksessa.
2. Vaihe 6 "Policy engine" on vain osittain valmis.
   Relay-candidate-polku on listapohjainen osin, mutta compatibility-lukuja ja
   fixed-id-polkuja on edelleen.
3. Vaihe 7 "Dispatch state applier" on vain osittain valmis.
   Active-device-lista on device-id -pohjainen, mutta canonical ordering,
   decision text ja write trace sisaltavat edelleen fixed-id oletuksia.
4. Vaihe 8 "Writerit" on osittain valmis.
   Writer loop iteroi registrya, mutta relay fallbackit ja testipinnat eivat
   viela todista n-releista tuotantopolulla.
5. Vaihe 10 "Testit" ei voi olla valmis ennen kuin 3 relay + 2 EV
   contract/e2e-testit todistavat saman polun.

Seuraava sessio kannattaa kasitella tama dokumentti authoritative handoffina ja
paivittaa vanhan suunnitelman status vasta kun alla olevat hyvaksyntakohdat
ovat vihreat.

## Toteutussuunnitelma

### Step 1: korjaa runtime entity -registry aidosti n-deviceksi

Status: completed 2026-06-22.

Tavoite:

`build_runtime_entities_from_grouped_config(...)` palauttaa device-kohtaisen
registry-rakenteen kaikille `RELAY`- ja `EV_CHARGER`-deviceille ilman, etta
uusia top-level avaimia tarvitaan.

Toteutunut:

1. Contract-test todistaa `RELAY3`-devicen `entities['devices']['RELAY3']`
   -rekisterissa.
2. Contract-test todistaa toisen EV-laturin `entities['devices']['EV_GARAGE']`
   -rekisterissa.
3. Contract-test todistaa, ettei `actuator_relay3` tai `relay3` ilmesty
   top-level compatibility-aliakseksi.

Tehtavat:

1. Varmista, etta `entities['devices'][device_id]` sisaltaa kaikille releille:
   `enabled`, `surplus_allowed`, `force_on`, `priority`, `max_absorb_w`.
2. Varmista, etta kaikille EV-latureille mukana ovat:
   `enabled`, `current_a`, `current_min_a`, `current_max_a`,
   `current_step_a`, `phases`, `voltage_v`, `force_current_a`,
   `surplus_allowed`, `priority`.
3. Pida `relay1_*`, `relay2_*`, `actuator_relay1`, `actuator_relay2`
   compatibility-aliaksina vain nykyisia testeja ja dashboardeja varten.
4. Ala lisaa pysyvaksi ratkaisuksi `actuator_relay3`-tyyppisia uusia
   litteita aliaksia tuotantopolulle. Testien tulee oppia lukemaan
   `ENT['devices']['RELAY3']['enabled']`.

Hyvaksynta:

```bash
python3 -m pytest -q tests/unit/test_core_config.py tests/unit/test_device_read_model.py tests/contract/test_runtime_entity_registry_contract.py
```

Jos `tests/contract/test_runtime_entity_registry_contract.py` puuttuu tai on
eri nimella, lisaa/uudelleenkayta contract-testi, joka todistaa `RELAY3` ja
toinen EV-laite `entities['devices']` registrysta.

### Step 2: generalisoi e2e-harness device-id -pohjaiseksi

Status: completed.

Toteutettu nykyisessa sessiossa:

1. `tests/e2e_entity/scenario_runner.py` sai `device_entity(device_id, field)`
   helperin.
2. `seed_active_surplus_devices(...)` tukee nyt:
   - `active_device_ids`
   - `relay_states={device_id: bool}`
   - `ev_states={device_id: {...}}`
   Nykyiset `actuator_relay1`, `actuator_relay2`,
   `actuator_ev_enabled`, `actuator_ev_current_a` ja
   `actuator_battery_setpoint_w` parametrit sailytettiin compatibilityna.
3. `tests/e2e_entity/net_zero_priority_order_quarter_3_relays` kayttaa nyt
   omaa 3 releen `scenario_steps.py` moduulia, ei 2 releen skenaariota.
4. RELAY3:n entityt haetaan testissa `ENT['devices']['RELAY3']` registryn
   kautta helperilla, eika top-level `ENT['actuator_relay3']` -avainta enaa
   tarvita.
5. 3 releen e2e-odotukset paivitettiin oikeaksi 3 releen ketjuksi:
   aktivointi `RELAY1 -> EV_CHARGER -> RELAY2 -> RELAY3` ja release
   `RELAY3 -> RELAY2 -> EV_CHARGER -> RELAY1`.
6. `ems_policy_engine.read_measurements(...)` tayttaa relay runtime-stateen
   nyt geneerisen `active`-kentän `active_surplus_devices`-tilasta. Ilman
   tata RELAY3 aktivoitui dispatch-statessa, mutta seuraava policy-kierros ei
   nahnyt sita aktiivisena. Tama on Step 4:n suuntaan tehty pieni
   tuotantopolun osakorjaus.

Varmennettu:

```bash
python3 -m pytest -q tests/e2e_entity/net_zero_priority_order_quarter_3_relays
# 3 passed

python3 -m pytest -q tests/unit/test_core_config.py tests/unit/test_device_read_model.py tests/contract/test_runtime_entity_registry_contract.py
# 17 passed

python3 -m pytest -q tests/e2e_entity/net_zero_priority_order_quarter
# 3 passed
```

Tavoite:

E2E-skenaariot eivat tarvitse `ENT['actuator_relay3']`-avainta. Ne kayttavat
joko device-registrya tai helperia, joka palauttaa actuator-entityn device-id:n
perusteella.

Tehtavat:

1. Lisaa helperi esimerkiksi `entity_for_device(h/ENT, device_id, field)` tai
   testien oma pieni funktio:
   `ENT['devices'][device_id]['enabled']`.
2. Paivita 3 relay -e2e kayttamaan `RELAY3` device-id -pohjaista entitya.
3. Generalisoi `seed_active_surplus_devices(...)` ottamaan:
   - `active_device_ids`
   - `relay_states={device_id: bool}`
   - `ev_states={device_id: {...}}`
4. Sailyta nykyiset `actuator_relay1`, `actuator_relay2`,
   `actuator_ev_enabled` convenience-parametrit compatibilityna, mutta uusi
   testi kayttaa device-id mappeja.
5. Paivita `_LEGACY_VALUE_ENTITY_IDS` vain jos e2e-harness vahingossa sallii
   vanhoja scalar-policy entityja uudelleen.

Hyvaksynta:

```bash
python3 -m pytest -q tests/e2e_entity/net_zero_priority_order_quarter_3_relays
```

### Step 3: dispatch state applier n-releille

Status: completed 2026-06-22.

Toteutettu nykyisessa sessiossa:

1. `ems_dispatch_state_applier.py` ei enaa kayta fixed
   `RELAY1`/`RELAY2`/`EV_CHARGER`/`HOME_BATTERY` -haaroja dispatch-
   aktivointiin, releaseen, active-listan normalisointiin tai CLEAR_ALL-
   vapautukseen.
2. Dispatch-komento ratkaistaan canonical `device_id`:ksi trace-kentasta
   `surplus_device_dispatch_device_id` tai tarvittaessa
   `surplus_device_targets[*].decision_name -> device_id` -mapista.
3. `decision` trace on nyt device-id -pohjainen, ja compatibility-
   `decision_name` raportoidaan erillisessa `device_dispatch_decision_name`
   -kentassa.
4. Write-trace labelit ovat geneerisia `on:<device_id>` /
   `off:<device_id>` -muotoja, eivat relay1/relay2/adjustable-haaroja.
5. Unit-testit todistavat RELAY3-aktivoinnin, RELAY3-releasen decision-name-
   fallbackilla ja CLEAR_ALL:n kaikille active surplus device-id:ille.

Varmennettu:

```bash
python3 -m pytest -q tests/unit/test_dispatch_state_applier.py tests/e2e_entity/net_zero_priority_order_quarter_3_relays
# 10 passed

python3 -m pytest -q tests/e2e_entity/net_zero_priority_order_quarter
# 3 passed
```

Tavoite:

Dispatch-applier kasittelee aktivoinnin, release-polun ja active-listan
device-id -pohjaisesti ilman fixed `RELAY1`/`RELAY2` -haaroja.

Tehtavat:

1. Korvaa fixed ordering `RELAY1`, `EV_CHARGER`, `HOME_BATTERY`, `RELAY2`
   jarjestyksella, joka pohjautuu policy traceen:
   - `surplus_device_targets`
   - nykyinen `active_surplus_device_ids`
   - tarvittaessa configin `relay_device_ids` / `ev_device_ids`
2. Paivita `_decision_text_from_device_command(...)` kayttamaan device-id:ta
   ja targetin `decision_name`-arvoa vain compatibility traceen.
3. Paivita `_apply_device_dispatch(...)` niin, etta se ei tunne vain
   `RELAY1`/`RELAY2`.
4. Varmista, etta `CLEAR_ALL` vapauttaa kaikki active surplus device-id:t,
   ei vain tunnettua adjustable-joukkoa.

Hyvaksynta:

```bash
python3 -m pytest -q tests/unit/test_dispatch_state_applier.py tests/e2e_entity/net_zero_priority_order_quarter_3_relays
```

### Step 4: policy engine n-releille

Status: completed 2026-06-22.

Toteutettu nykyisessa sessiossa:

1. `compute_net_zero_engine_outputs(...)` normalisoi relay runtime-state-mapin
   konfiguroidun relay-device-listan perusteella, ei kovakoodatuilla
   `RELAY1`/`RELAY2`-avaimilla.
2. Vanhat `relay1_*` ja `relay2_*` scalar-parametrit sailyvat compatibility-
   fallbackina vain ensimmaiselle ja toiselle konfiguroidulle releelle, jos
   device-id -kohtainen runtime-state ei anna kenttaa.
3. Force-on rising edge -fallback rakentuu konfiguroiduista relay-id:ista,
   joten tuotantopolku ei tarvitse fixed `RELAY1`/`RELAY2` -oletusta.
4. Unit-test todistaa, etta `RELAY3` tulee grouped-configin device registrysta
   `surplus_device_targets`- ja `device_policies`-ulostuloihin ilman scalar-
   riippuvuutta.

Varmennettu:

```bash
python3 -m pytest -q tests/unit/test_engine.py tests/unit/test_surplus_device_targets.py tests/e2e_entity/net_zero_priority_order_quarter_3_relays
# 44 passed
```

Tavoite:

Policy engine lukee relay runtime-statea device registrysta ja tuottaa
relay-politiikat kaikille relay-deviceille.

Tehtavat:

1. Varmista, etta `_relay_runtime_candidates(...)` saa kaikkien relay-devicejen
   runtime-state-mapin, ei vain `RELAY1` ja `RELAY2`.
2. Poista tuotantopolun riippuvuus `relay1_surplus_allowed`,
   `relay2_surplus_allowed`, `relay1_force_on`, `relay2_force_on`.
3. Sailyta nuo scalarit vain compatibility-lukuna, jos vanhat testit tai
   dashboardit tarvitsevat niita.
4. Paivita `NetZeroOutputs` / trace niin, etta relay-policies todistetaan
   `device_policies` ja `surplus_device_targets` kautta.

Hyvaksynta:

```bash
python3 -m pytest -q tests/unit/test_engine.py tests/unit/test_surplus_device_targets.py tests/e2e_entity/net_zero_priority_order_quarter_3_relays
```

### Step 5: writer n-releille

Status: completed 2026-06-22.

Toteutettu nykyisessa sessiossa:

1. `_write_relay_actuator(...)` ratkaisee relay-actuatorin ensisijaisesti
   `entities['devices'][device_id]['enabled']` -polusta.
2. `actuator_relay1` ja `actuator_relay2` sailyvat vain compatibility-
   fallbackeina vanhalle pinnalle.
3. Jos device-id:lle ei loydy registry-entitya eika compatibility-fallbackia,
   writer palauttaa `missing_actuator_entity` eika kirjoita tyhjaan entityyn.
4. Unit-test todistaa, etta `RELAY3` saa device-policyssa `enabled=True` ja
   writer-loop kirjoittaa `switch.relay_3_2`.

Varmennettu:

```bash
python3 -m pytest -q tests/unit/test_writer_semantics.py tests/e2e_entity/net_zero_priority_order_quarter_3_relays
# 22 passed
```

Tavoite:

Writer kirjoittaa jokaisen `kind == 'RELAY'` devicen oman `adapter.enabled`
entityn kautta.

Tehtavat:

1. Varmista, etta `_write_relay_actuator(...)` saa actuator-entityn aina
   `entities['devices'][device_id]['enabled']` kautta.
2. Poista tuotantopolun tarve fallbackeille `actuator_relay1` ja
   `actuator_relay2`.
3. Pida fallbackit vain compatibilityna vanhalle configille.
4. Lisaa unit-test, jossa `RELAY3` saa policyssa `enabled=True` ja writer
   kirjoittaa `switch.relay_3_2`.

Hyvaksynta:

```bash
python3 -m pytest -q tests/unit/test_writer_semantics.py tests/e2e_entity/net_zero_priority_order_quarter_3_relays
```

### Step 6: ensimmainen n-EV support boundary

Status: completed 2026-06-22.

Toteutettu nykyisessa sessiossa:

1. Engine tunnistaa `EV_CHARGER`-roolin nyt device kindin perusteella, ei vain
   literal `EV_CHARGER` -device-id:lla.
2. Valittu EV ratkaistaan seka `adjustable_surplus_load`- etta
   `adjustable_primary_load`-roolista, joten esimerkiksi `EV_GARAGE` voidaan
   valita ilman etta ensimmainen EV kaappaa policy-statea.
3. Valitun EV:n min/max current, step, phases, force-current ja hard-off
   asetukset luetaan kyseisen devicen adapter/policy-konfigista.
4. Muut EV:t saavat inactive `DevicePolicy(enabled=False, target_w=0)`.
5. Writer lataa grouped runtime entity registryn ja yhdistaa sen legacy
   `ENT`-fallbackiin, jotta uudet EV-device-id:t paatyvat writerin
   `entities['devices']`-polulle.
6. Contract-test todistaa kaksi EV device-id:ta `core.devices`,
   `entities['devices']`, `device_policies` ja writer-tracessa.

Varmennettu:

```bash
python3 -m pytest -q tests/unit/test_engine.py tests/unit/test_writer_semantics.py tests/contract/test_grouped_config_runtime_parity.py
# 65 passed
```

Tavoite:

N-EV ei tarkoita viela HAEO:n optimointia usealle EV:lle. Ensimmainen
tuotantokelpoinen boundary on:

1. registryssa voi olla useampi `EV_CHARGER`
2. yksi EV voi olla valittu `adjustable_surplus_load` tai
   `adjustable_primary_load`
3. muut EV:t pysyvat inactive policyssa
4. previous-device-state ja writer trace ovat device-id -kohtaisia

Tehtavat:

1. Lisaa contract-test, jossa YAML:ssa on `EV_MAIN` ja `EV_GARAGE`.
2. Valitse `adjustable_surplus_load=EV_GARAGE` ja varmista, etta policy ja
   writer targetoivat vain sita.
3. Varmista, etta `previous_ev_device_states` paivittyy valitulle EV device-id:lle.
4. Varmista, etta inactive EV saa `DevicePolicy(enabled=False, target_w=0)`.
5. Ala viela toteuta round-robinia, multi-EV split dispatchia tai HAEO:n usean
   EV:n optimointia.

Hyvaksynta:

```bash
python3 -m pytest -q tests/unit/test_engine.py tests/unit/test_writer_semantics.py tests/contract/test_grouped_config_runtime_parity.py
```

Lisaehto: uusi n-EV contract-test todistaa kaksi EV device-id:ta
`core.devices`, `entities['devices']`, `device_policies` ja writer-tracessa.

### Step 7: paivita suunnitelmadokumentin status totuuden mukaiseksi

Tavoite:

`surplusloads_to_support_more_flexibiity.md` ei saa antaa seuraavalle
kehittajalle kuvaa, etta n-device-polku on jo valmis, jos se ei ole.

Tehtavat:

1. Muuta vaiheet 4, 6, 7, 8, 10 tarvittaessa tilaan `partial`.
2. Lisaa toteutuneiden kohtien alle maininta nykyisesta rajasta:
   registry valmis, mutta e2e/runtime/harness ei viela todista n-laitteita.
3. Kun ylla olevat testit menevat lapi, palauta status `completed`.

Hyvaksynta:

```bash
rg -n "0-n relay / 0-n EV|completed|partial|RELAY3|EV2" surplusloads_to_support_more_flexibiity.md
```

Dokumentti vastaa todellista testattua tilaa.

### Step 8: release-validaatio

Kun Steps 1-7 ovat valmiit:

```bash
python3 -m pytest -q tests/unit/test_core_config.py tests/unit/test_device_read_model.py tests/unit/test_surplus_device_targets.py tests/unit/test_dispatch_state_applier.py tests/unit/test_writer_semantics.py tests/unit/test_engine.py
python3 -m pytest -q tests/contract
python3 -m pytest -q tests/e2e_entity/net_zero_priority_order_quarter tests/e2e_entity/net_zero_priority_order_quarter_3_relays
python3 -m pytest -q tests/e2e_entity
python3 -m pytest -q tests
```

Hyvaksynta:

1. Vanha 2 relay + 1 EV e2e pysyy vihreana.
2. Uusi 3 relay e2e on vihrea.
3. Uusi 2 EV contract tai e2e on vihrea valitulle single-adjustable EV:lle.
4. `rg -n "actuator_relay3" tests/e2e_entity` ei nayta tuotantotavaksi
   litteaa top-level aliasia. Jos osumia on, niiden tulee olla vain
   compatibility-testissa.

## Tarkeat varoitukset seuraavalle sessiolle

1. Ala ratkaise `KeyError: actuator_relay3` lisaamalla vain uusi pysyva
   `actuator_relay3` top-level alias ja jatkamalla samaa mallia. Se korjaa
   yhden testin, mutta ei n-relearkkitehtuuria.
2. Pida compatibility aliasit rajattuina vanhaan relay1/relay2-pintaan.
   Uudet testit ja uusi tuotantologiikka kayttavat `entities['devices']`.
3. Monen EV:n tuki kannattaa rajata ensin "multiple configured, one selected"
   -malliin. Multi-EV power split ja HAEO multiple-EV ovat eri tyopaketti.
4. Jos testit alkavat odottaa `ADJUSTABLE`-teksteja, tarkista ensin onko kyse
   compatibility decision-namesta vai canonical device-id:sta. Canonical trace
   pitaa ensisijaisesti todistaa `device_id`-kentilla.
5. Tyopuussa on paljon muita muutoksia. Ala reverttoi niita ilman erillista
   pyyntoa.

## Aloituskomennot seuraavalle sessiolle

```bash
git status --short
python3 -m pytest -q tests/e2e_entity/net_zero_priority_order_quarter_3_relays
rg -n "relay1|relay2|RELAY1|RELAY2|EV_CHARGER|actuator_relay" modules/ems_adapter modules/ems_core ems_*.py tests/e2e_entity
```

Ensimmainen odotettu failure on todennakoisesti:

```text
KeyError: 'actuator_relay3'
```

Korjaa se ensisijaisesti siirtamalla uusi 3 relay e2e kayttamaan
`ENT['devices']['RELAY3']['enabled']` -tyyppista device-registry-polkua ja
generalisoimalla harness-seedaus device-id-mapille.
