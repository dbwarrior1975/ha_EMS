# Legacy-Free Release Handoff

Paivitetty: 2026-06-21

## Tarkoitus

Tama dokumentti kuvaa, mita puuttuu ennen kuin EMS:n surplus/load-polku voidaan
julkaista "legacy-vapaana". Tausta: surplus-kuormien joustavoittamisen vaiheet
A-C on nyt tehty kaytannon tasolla, mutta koodissa on yha yhteensopivuus- ja
diagnostiikkapintoja, jotka estavat legacy-vapaan releasen ilman lisasiivousta.

Tama on handoff seuraavaa sessiota varten. Aloita lukemalla myos:

1. [surplusloads_handoff.md](/home/virtamik/code/ha_EMS/docs/archive/surplusloads_handoff.md)
2. [surplusloads_to_support_more_flexibiity.md](/home/virtamik/code/ha_EMS/docs/archive/surplusloads_to_support_more_flexibiity.md)

## Nykyinen vahvistettu tila

Viimeisin koko testiajo taman tyopaketin jalkeen:

```bash
python3 -m pytest -q tests
```

Tulos:

```text
210 passed, 1 xfailed
```

Ainoa tunnettu `xfail`:

- `tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable/...`
- syy: tuleva EMS-internal HAEO combo -semantiikka, ei regressio

## Mita valmistui A-C-vaiheissa

### Vaihe A

- `CoreConfig.devices` on kanoninen device-registry.
- `CoreConfig.ev_charger`, `CoreConfig.relay1` ja `CoreConfig.relay2` ovat nyt
  yhteensopivuusnakymia, jotka johdetaan registrysta.
- `config_loader.py` ja `device_read_model.py` osaavat kasitella custom EV/relay
  device-id:ita paremmin kuin aiemmin.

### Vaihe B

- `previous_device_state` ei ole enaa vain yhden EV:n muistimalli.
- Engine ottaa vastaan `previous_ev_device_states`-mapin ja paivittaa valitun
  EV:n statea per `device_id`.
- Policy-loop julkaisee `previous_device_state`-sensorin attribuutteihin
  `device_states`-mapin legacy-top-level-kenttien rinnalle.

### Vaihe C

- Policy trace ilmoittaa kanonisen sopimuksen:
  - `policy_trace_canonical_contract = device_policies`
- Policy trace merkitsee scalarit legacy-diagnostiikaksi:
  - `policy_trace_legacy_contract = diagnostic_scalars_legacy`
  - `legacy_policy_scalars`
- Writer trace ilmoittaa kanonisen sopimuksen:
  - `writer_trace_canonical_contract = devices`
- Writer trace merkitsee nimetyt device-aliakset legacyksi:
  - `writer_trace_legacy_contract = named_device_aliases_legacy`
- Contract-testit lukevat writerin device-kohtaiset tulokset `devices`-mapista.

## Miksi tama ei ole viela legacy-vapaa release

Legacy-vapaa release vaatii, etta tuotantopolku ei tarvitse eika julkaise
vanhoja scalar-, alias- tai fixed-id-sopimuksia. Talla hetkella legacya on viela
useassa kategoriassa.

## Release-blokkerit

### 1. Policy-outputin scalar-peilit ovat yha top-level trace-kenttia

Tiedosto:

- [modules/ems_core/diagnostics/decision_trace.py](/home/virtamik/code/ha_EMS/modules/ems_core/diagnostics/decision_trace.py)

Nykytila:

- `ev_current_a`
- `relay1_command`
- `relay2_command`

Ne ovat jo merkitty `legacy_policy_scalars`-mapin alle, mutta ne julkaistaan
yha myos top-level-attribuutteina. Legacy-vapaa release vaatii toisen naista:

- poista top-level scalarit kokonaan, tai
- pidetaan ne vain erillisessa explicit deprecated/compat adapterissa, joka ei
  kuulu release-contractiin.

Hyvaksynta:

```bash
rg -n "attrs\\['ev_current_a'\\]|attrs\\['relay1_command'\\]|attrs\\['relay2_command'\\]|'ev_current_a': outputs.ev_current_a|'relay1_command': outputs.relay1_command|'relay2_command': outputs.relay2_command" modules ems_*.py
```

Ei loydy top-level policy trace -julkaisua muualta kuin mahdollisesta
deprecated adapterista.

### 2. Writer trace julkaisee yha legacy-nimetyt aliakset

Tiedosto:

- [ems_actuator_writers.py](/home/virtamik/code/ha_EMS/ems_actuator_writers.py)

Nykytila:

- kanoninen: `attrs['devices']`
- legacy-aliaset:
  - `attrs['ev']`
  - `attrs['relay1']`
  - `attrs['relay2']`
  - paluuarvon `result['ev']`, `result['relay1']`, `result['relay2']`

Legacy-vapaa release vaatii, etta writerin julkaistu sopimus on vain:

- `victron`
- `devices`
- `writer_trace_canonical_contract`

Hyvaksynta:

```bash
rg -n "attrs\\['ev'\\]|attrs\\['relay1'\\]|attrs\\['relay2'\\]|result\\['ev'\\]|result\\['relay1'\\]|result\\['relay2'\\]|writer_trace_legacy_contract" ems_actuator_writers.py tests
```

Tulos on tyhja, tai osumat ovat vain nimenomaisessa deprecated-contract-testissa,
jos sellainen pidetaan releasea edeltavassa siirtymaversiossa.

### 3. Engine rakentaa yha legacy dispatch/target -peileja

Tiedostot:

- [modules/ems_core/net_zero/engine.py](/home/virtamik/code/ha_EMS/modules/ems_core/net_zero/engine.py)
- [modules/ems_core/net_zero/surplus_device_targets.py](/home/virtamik/code/ha_EMS/modules/ems_core/net_zero/surplus_device_targets.py)
- [modules/ems_core/domain/models.py](/home/virtamik/code/ha_EMS/modules/ems_core/domain/models.py)

Nykytila:

- `SurplusTargetConfig` ja `SurplusDispatchDecision` legacy-nimilla ovat yha
  mukana parity-polussa.
- `device_targets_to_legacy_targets`
- `device_dispatch_to_legacy_dispatch`
- `surplus_dispatch_decision_role = ha_compatibility_mirror`
- `NetZeroOutputs` kantaa yha scalareita:
  - `ev_current_a`
  - `relay1_command`
  - `relay2_command`

Legacy-vapaa release vaatii, etta canonical output on ensisijaisesti:

- `device_policies`
- `surplus_device_targets`
- `surplus_device_dispatch_*`
- `active_surplus_devices`

Ja legacy-parity voidaan poistaa tai rajata erilliseen adapterikerrokseen.

Hyvaksynta:

```bash
rg -n "device_targets_to_legacy_targets|device_dispatch_to_legacy_dispatch|surplus_dispatch_decision_role|ha_compatibility_mirror|relay1_command|relay2_command" modules/ems_core ems_policy_engine.py tests
```

Release-valmiissa tilassa osumat eivat saa olla tuotantomoottorin kanonisessa
polussa.

### 4. Runtime/config alias -pinta on viela relay1/relay2/EV_CHARGER-painotteinen

Tiedostot:

- [modules/ems_adapter/config_loader.py](/home/virtamik/code/ha_EMS/modules/ems_adapter/config_loader.py)
- [modules/ems_adapter/runtime_context.py](/home/virtamik/code/ha_EMS/modules/ems_adapter/runtime_context.py)
- [EMS_config.yaml](/home/virtamik/code/ha_EMS/EMS_config.yaml)
- [example_EMS_config.yaml](/home/virtamik/code/ha_EMS/example_EMS_config.yaml)

Nykytila:

- `build_runtime_aliases` rakentaa edelleen legacy runtime-avaimia:
  - `relay1_power_kw`
  - `relay2_power_kw`
  - `relay1_force_on`
  - `relay2_force_on`
  - `charger_current`
  - `actuator_ev_current_a`
  - jne.
- `build_runtime_entities_from_grouped_config` nostaa naita samoja avaimia
  edelleen `ENT`-tasolle.
- Tuotantoesimerkki kayttaa viela device-id:ita:
  - `EV_CHARGER`
  - `RELAY1`
  - `RELAY2`

Legacy-vapaa release ei valttamatta vaadi, etta tuotantoesimerkin id:t
nimetaan uusiksi, mutta se vaatii, ettei runtime-logiikka oleta juuri naita
id:ita. Jos release-lupaus tarkoittaa myos "ei legacy-nimisia entity-avaimia",
nama aliasit pitaa poistaa julkisesta contractista.

Hyvaksynta:

```bash
rg -n "relay1_|relay2_|charger_current|actuator_ev_current_a|EV_CHARGER|RELAY1|RELAY2" modules/ems_adapter ems_*.py tests/contract
```

Arvioi osumat yksi kerrallaan:

- sallittu: YAML-esimerkin device-id, jos release-sopimus sallii nimetyt id:t
- sallittu: testidata, joka varmistaa backward compatibilitya
- ei sallittu: tuotantopolku, joka vaatii tietyn id:n tai scalar-aliasin

### 5. CoreConfig ja EmsConfig kantavat edelleen compatibility-rakenteita

Tiedostot:

- [modules/ems_core/domain/models.py](/home/virtamik/code/ha_EMS/modules/ems_core/domain/models.py)
- [modules/ems_adapter/config_loader.py](/home/virtamik/code/ha_EMS/modules/ems_adapter/config_loader.py)
- [modules/ems_adapter/device_read_model.py](/home/virtamik/code/ha_EMS/modules/ems_adapter/device_read_model.py)

Nykytila:

- `EmsConfig` on edelleen laaja scalar legacy-config.
- `build_core_config_from_legacy_config` on edelleen olemassa.
- `build_ems_config_from_core_config` palauttaa legacy scalar -nakyman.
- `CoreConfig` sisaltaa edelleen deprecated/yhteensopivuuskentat:
  - `ev_charger`
  - `relay1`
  - `relay2`
  - `relay1_power_kw`
  - `relay2_power_kw`
  - `relay1_priority`
  - `relay2_priority`
  - `ev_priority`

Legacy-vapaa release vaatii paatoksen:

1. Poistetaanko `EmsConfig`-polku kokonaan tuotantoruntimesta?
2. Jatetaanko se vain testien/adapterien deprecated-poluksi?
3. Onko `CoreConfig` allowed to expose deprecated convenience fields, jos
   tuotantopolku ei kayta niita?

Suositus:

- Jata yksi selkea deprecated adapter -moduuli, jos backward compatibilitya
  tarvitaan.
- Poista legacy-kentat canonical domain -malleista releaseen mennessa, tai
  merkitse ne nimella, joka tekee niiden roolin selvaksi.

### 6. HAEO net-zero plan on viela HOME_BATTERY/EV_CHARGER -spesifi

Tiedosto:

- [modules/ems_core/integrations/haeo_net_zero_plan.py](/home/virtamik/code/ha_EMS/modules/ems_core/integrations/haeo_net_zero_plan.py)

Nykytila:

- HAEO-plan valitsee viela `HOME_BATTERY` ja `EV_CHARGER` nimilla.
- Tunnettu xfail liittyy HAEO combo -semantiikkaan.

Jos legacy-vapaa release tarkoittaa vain surplus relay/EV -polkua, tama voidaan
rajata pois ensimmaisesta releasesta. Jos se tarkoittaa koko EMS:n generic
device -julkaisua, tama on blocker.

Hyvaksynta:

```bash
python3 -m pytest -q tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable
```

Tama ei saa olla xfail ennen kuin koko EMS voidaan sanoa generic-device
releaseksi.

## Suositeltu toteutusjarjestys seuraavassa sessiossa

### Step 1: Paata release-sopimuksen rajaus

Kirjaa lyhyesti dokumenttiin tai PR-kuvaukseen, tarkoittaako "legacy-vapaa":

- vain tuotantoruntime ei lue legacy-sensoreita
- vai myos traceista poistetaan legacy-aliaset
- vai myos domain-malleista poistetaan scalar legacy -kentat
- vai myos YAML-esimerkit eivat kayta `EV_CHARGER`, `RELAY1`, `RELAY2` -nimia

Ilman tata rajausta "legacy-vapaa" ja "backward compatible" menevat sekaisin.

Paatos 2026-06-21:

- legacyt poistetaan tuotantopolusta mahdollisimman pitkalle
- writer- ja policy-tracen legacy-contractit poistetaan release-sopimuksesta
- runtime ei saa vaatia legacy-sensoreita tai named-alias-julkaisuja
- domain/config compatibility-rakenteita saa siivota, kunhan tuotantopolku pysyy ehjana
- YAML-esimerkit saavat toistaiseksi edelleen kayttaa nykyisia device-id:ita:
  - `EV_CHARGER`
  - `RELAY1`
  - `RELAY2`

Toisin sanoen: current device-id naming exampleissa ei ole blocker, mutta
legacy release-contractit ja legacy runtime-oletukset ovat.

### Step 2: Poista writer-tracen legacy-aliakset

Kohde:

- [ems_actuator_writers.py](/home/virtamik/code/ha_EMS/ems_actuator_writers.py)

Poista:

- `attrs['ev']`
- `attrs['relay1']`
- `attrs['relay2']`
- `result['ev']`
- `result['relay1']`
- `result['relay2']`
- `writer_trace_legacy_contract`

Paivita testit lukemaan vain:

- `writer_trace['attrs']['devices'][device_id]`
- loop-resultin `result['devices'][device_id]`

### Step 3: Poista policy-tracen top-level scalarit

Kohde:

- [modules/ems_core/diagnostics/decision_trace.py](/home/virtamik/code/ha_EMS/modules/ems_core/diagnostics/decision_trace.py)

Poista top-level:

- `ev_current_a`
- `relay1_command`
- `relay2_command`

Jos scalarit tarvitaan debugiin, pida ne vain:

- `legacy_policy_scalars`

Tai siirra ne erilliseen deprecated trace -sensoriin.

### Step 4: Poista engine parity legacy -polku

Kohteet:

- [modules/ems_core/net_zero/engine.py](/home/virtamik/code/ha_EMS/modules/ems_core/net_zero/engine.py)
- [modules/ems_core/net_zero/surplus_device_targets.py](/home/virtamik/code/ha_EMS/modules/ems_core/net_zero/surplus_device_targets.py)
- [modules/ems_core/domain/models.py](/home/virtamik/code/ha_EMS/modules/ems_core/domain/models.py)

Tavoite:

- `NetZeroOutputs` ei tarvitse `ev_current_a`, `relay1_command`,
  `relay2_command` kanonisina kenttina.
- `surplus_device_*` ei tarvitse vertailla itseaan legacy `SurplusTargetConfig`
  -polkuun.
- `surplus_dispatch_decision_role = ha_compatibility_mirror` poistuu.

Tama on riskialttein vaihe, koska suuri osa unit-testeista tarkistaa viela
legacy-outputteja suoraan. Tee tama vasta Step 2-3 jalkeen.

### Step 5: Rajaa tai poista `EmsConfig` compatibility

Kohteet:

- [modules/ems_core/domain/models.py](/home/virtamik/code/ha_EMS/modules/ems_core/domain/models.py)
- [modules/ems_adapter/config_loader.py](/home/virtamik/code/ha_EMS/modules/ems_adapter/config_loader.py)
- [modules/ems_adapter/device_read_model.py](/home/virtamik/code/ha_EMS/modules/ems_adapter/device_read_model.py)

Suositus:

- Tee ensin `rg -n "EmsConfig|build_core_config_from_legacy_config|build_ems_config_from_core_config|_device_configs_from_legacy_config" modules ems_*.py tests`.
- Jos tuotantopolku ei tarvitse naita, siirra ne deprecated adapter -osioon tai
  poista.
- Paivita testit rakentamaan `CoreConfig` suoraan grouped configista.

### Step 6: Paivita dokumentaatio ja release notes

Kohteet:

- [README.md](/home/virtamik/code/ha_EMS/README.md)
- [operointi.md](/home/virtamik/code/ha_EMS/docs/user/operointi.md)
- [arkkitehtuuri.md](/home/virtamik/code/ha_EMS/docs/dev/arkkitehtuuri.md)
- [releasenotes.md](/home/virtamik/code/ha_EMS/docs/user/releasenotes.md)
- [hardcoded_not_read_from_YAML.md](/home/virtamik/code/ha_EMS/docs/archive/hardcoded_not_read_from_YAML.md)

Nykyiset dokumentit sisaltavat yha ristiriitaisia viesteja:

- osa sanoo legacy-peilien olevan poistettuja
- osa kuvaa ne edelleen olemassa oleviksi
- osa kuvaa scalar-tracet diagnostisiksi

Legacy-vapaa release tarvitsee yhden paivitetyn totuuden:

- canonical input config
- canonical policy output
- canonical dispatch state
- canonical writer trace
- deprecated/poistetut pinnat

## Release-hyvaksyntakriteerit

Ennen legacy-vapaata releasea seuraavien tulisi pitaa:

1. `python3 -m pytest -q tests` menee lapi.
2. `tests/smoke/test_pyscript_ast_compat.py` menee lapi.
3. Contract-testit eivat odota writer-tracen `ev`, `relay1`, `relay2`
   -aliaksia.
4. Policy-tracen canonical pinta on `device_policies`; legacy-scalarit eivat
   ole top-level release-contractissa.
5. Dispatch state julkaisee vain `active_surplus_devices` device-id-listana.
6. Writer lukee vain `device_policies` ja kirjoittaa vain `devices`-registryssa
   olevia laitteita.
7. `rg -n "policy_ev_current_a|policy_relay1_command|policy_relay2_command" ems_*.py modules`
   ei loyda tuotantolukijoita.
8. `rg -n "writer_trace_legacy_contract|policy_trace_legacy_contract|named_device_aliases_legacy|diagnostic_scalars_legacy" ems_*.py modules`
   ei loyda release-contractiin jaavia legacy-sopimuksia.

## Aloituskomennot seuraavaan sessioon

```bash
git status --short
python3 -m pytest -q tests
rg -n "legacy|compat|policy_trace_legacy|writer_trace_legacy|legacy_policy_scalars|named_device_aliases|ev_current_a|relay1_command|relay2_command" modules ems_*.py tests
rg -n "attrs\\['ev'\\]|attrs\\['relay1'\\]|attrs\\['relay2'\\]|result\\['ev'\\]|result\\['relay1'\\]|result\\['relay2'\\]" ems_actuator_writers.py tests
rg -n "EmsConfig|build_core_config_from_legacy_config|build_ems_config_from_core_config|_device_configs_from_legacy_config" modules ems_*.py tests
```

## Tyopuuhuomio

Tyopuu on ollut tassa vaiheessa likainen jo ennen tata dokumenttia. Ala tee
`git reset` tai revertteja ilman erillista pyyntoa. Tarkista ennen PR:aa:

- repojuuren zip-artefaktit
- [final_cleaning.md](/home/virtamik/code/ha_EMS/docs/archive/final_cleaning.md)
- [surplusloads_handoff.md](/home/virtamik/code/ha_EMS/docs/archive/surplusloads_handoff.md)
- [surplusloads_to_support_more_flexibiity.md](/home/virtamik/code/ha_EMS/docs/archive/surplusloads_to_support_more_flexibiity.md)
