# Vaihesuunnitelma: E2E NET_ZERO raw runtime inputs + expect_derived

Lahdedokumentti: `docs/dev/codex_task_e2e_raw_runtime_inputs_with_derived_intent.md`

Review-tarkennukset huomioitu dokumentista:
`docs/dev/codex_review_notes_e2e_raw_inputs_phase_plan.md`

## Tiivis arvio

Muutos on tehtavissa hyvin hallitusti. Nykyinen koodi on jo lahella tavoitetta:

- Tuotantopolku lukee `grid_power_w`, `quarter_energy_balance_kwh` ja `pv_power_w` runtime-entiteeteista.
- `ems_policy_engine.py` kutsuu jo tuotannon `derive_net_zero_inputs()`-funktiota.
- E2E-harnessissa on jo legacy-yhteensopivuuskerros, joka mapittaa vanhat `rpnz_w`, `required_power_consumption_kw` ja `pv_power_kw` testialiaksiksi.
- Testiapureissa on jo `runtime_inputs_for_net_zero()` ja `balance_for_rpnz_w()`, jotka ratkaisevat raw-inputit legacy-intention perusteella.

Isoin ero lahdedokumenttiin on, etta nykyiset E2E-skenaariot eivat ole YAML-steppeja vaan Python-dikteja testitiedostoissa. Suunnitelma kannattaa siis toteuttaa nykyiseen Python-step-malliin, ei rakentaa erillista YAML-runneria.

## Nykytilan olennaiset tiedostot

- `tests/e2e_entity/scenario_harness.py`
  - Lisaa legacy-aliakset `h.ent`-karttaan.
  - Normalisoi legacy-runtime-syotteita metodissa `_normalize_legacy_runtime_inputs()`.
  - Monkey-patchaa policy-moduulin `derive_net_zero_inputs`-funktion metodissa `_run_policy_loop()`.
- `tests/e2e_entity/scenario_runner.py`
  - Ajaa stepit ja validoi `expect_policy`, `expect_device_policies`, `expect_dispatch_state`, `expect_writer_trace` ja `expect_values`.
  - Tahan kuuluu lisata `expect_derived`-validointi.
- `tests/helpers.py`
  - Sisaltaa jo `runtime_inputs_for_net_zero()`, joka kannattaa siirtaa tai kytkea e2e-kayttoon selkeammin.
- `modules/ems_core/net_zero/derived_inputs.py`
  - Tuotannon laskentafunktio ja golden-kaavat.
- `tests/unit/test_net_zero_derived_inputs.py`
  - Nykyiset yksikkotestit derive-kaavoille.

## Toteutettavuus ja rajaukset

Toteutettavissa heti:

- `expect_derived`-lohkon tuki Python-steppeihin.
- Toleranssit scalar- ja dict-muodossa.
- Fixture-virhe, jos raw runtime -syotteet eivat tuota odotettua derived-intentiota.
- Legacy-aliasten nimeaminen tai dokumentointi test-only migration -pinnaksi.
- Valikoitujen kriittisten skenaarioiden migraatio raw-inputeiksi.

Tehtava varoen:

- Monkey-patchin poisto. Sita ei kannata poistaa ennen kuin paaskenaariot eivat enaa tarvitse legacy-intenttia.
- Kaikkien skenaarioiden massamigraatio. Nykyisissa testeissa legacy-intentti ja `grid_power_w` ovat usein tietoisesti erillisia signaaleja; raakasyotteisiin siirto voi paljastaa aidosti muuttuneita odotuksia.

Ei kannata tehda tassa vaiheessa:

- Uutta YAML-skenaariomuotoa. Se ei ole nykyisen e2e-infran muoto, ja kasvattaisi muutoksen blast radiusia turhaan.
- Tuotannon `derive_net_zero_inputs()`-kaavojen muuttamista. Tama taski koskee e2e-fixtureiden realismia, ei business-logiikan uudelleentulkintaa.

## Vaihe 1: nimea legacy-polku eksplisiittiseksi migration-poluksi

Tavoite: vanha shim saa jaada, mutta sen kaytto ei saa nayttaa tuotannon runtime-polulta.

Muutokset:

1. Paivita `tests/e2e_entity/scenario_harness.py`:
   - Sailyta nykyiset `E['rpnz_w']`, `E['required_power_consumption_kw']`, `E['required_power_w']` ja `E['pv_power_kw']` aluksi taaksepain yhteensopivina aliaksina.
   - Ala tee pitkista legacy-aliaksista uutta suositeltua muotoa. Jos niita lisataan valiaikaisesti, dokumentoi ne poistettaviksi.
   - Suosi jatkossa yhta migration-only blokkia:

```python
'net_zero_intent': {
    'rpnz_w': 500,
    'required_power_consumption_kw': 2.6,
    'pv_power_kw': 8.0,
}
```

   - Kommentoi `_normalize_legacy_runtime_inputs()` ja `_derive_net_zero_inputs_for_test()` test-only migration -pinnaksi.

2. Paivita `tests/e2e_entity/scenario_runner.py`:
   - Lisaa varoitusluonteinen guard tai tekninen velka -kommentti, joka tekee selvaksi, etta legacy-intent on sallittu vain migration-ajaksi.
   - Ala viela kiella vanhoja avaimia, jotta nykyinen suite pysyy vihreana.

3. Lisaa tai paivita testit:
   - Yksikkotesti harnessin legacy-aliaksille.
   - Testi, etta legacy RPC/RPNZ edelleen vaikuttaa policy loopiin nykyisella tavalla.

Valmis, kun:

- Koko nykyinen testisetti menee lapi ilman skenaarioiden odotusarvomuutoksia.
- Koodista kay ilmi, etta legacy-polku ei ole tuotantopolku.

## Vaihe 2: lisaa expect_derived e2e-runneriin

Tavoite: step voi sanoa raw runtime -syotteiden tarkoittaman derived-intention ja runner tarkistaa sen tuotantofunktiolla.

Ehdotettu step-muoto:

```python
{
    'at_s': 135,
    'set': {
        E['grid_power_w']: 3390.1923076923076,
        E['quarter_energy_balance_kwh']: 0.002125,
        E['pv_power_w']: 1700.0,
    },
    'expect_derived': {
        'rpnz_w': -10,
        'required_power_consumption_kw': -3.4,
        'remaining_quarter_s': 765,
        'remaining_quarter_min': 13,
    },
}
```

Tuettava toleranssimuoto:

```python
'expect_derived': {
    'rpnz_w': {'value': -10, 'tolerance': 2},
    'required_power_consumption_kw': {'value': -3.4, 'tolerance': 0.01},
}
```

Muutokset:

1. Lisaa `scenario_runner.py`-tiedostoon apurit:
   - `_assert_expected_derived(idx, step, h)`
   - `_assert_expected_number(actual, expected_spec, context)`
   - `_effective_runtime_value(h, key)` tai vastaava, joka hakee raw-arvot harnessin efektiivisesta tilasta.

2. Laske actual-arvot aina tuotannon `derive_net_zero_inputs()`-funktiolla:
   - Importtaa suoraan `ems_core.net_zero.derived_inputs.derive_net_zero_inputs`.
   - Kayta deterministista aikaa, jolla step ajettiin: `step.get('at_s')` tai harnessin step-aika.
   - Syota `quarter_energy_balance_kwh` ja `grid_power_w` harnessin nykyisista raw-entiteettiarvoista `h.step()`-kutsun jalkeen.
   - Ala laske vain nykyisen stepin `set`-diktista, koska osa raw-arvoista voi periytya aiemmista stepeista.

3. Vertaile kentat:
   - `rpnz_w`
   - `required_power_w`
   - `required_power_consumption_kw`
   - `remaining_quarter_s`
   - `remaining_quarter_min`
   - `remaining_template_minutes` voidaan tukea aliaksena `remaining_quarter_min`-kenttaan, jos stepit halutaan kirjoittaa lahdedokumentin sanastolla.
   - halutessa `input_quality` ja `input_warnings`

4. Virheilmoituksen tulee olla fixture-virhe:
   - `Invalid E2E fixture: raw runtime inputs do not produce expected NET_ZERO derived intent`
   - Sisallyta step index, note, kentta, actual, expected ja tolerance.

5. Paata suoritusjarjestys:
   - Suositus: validoi `expect_derived` heti `h.step()`-kutsun jalkeen ennen policy-odotuksia.
   - Nain epakonsistentti fixture ei nayta policy-regressiolta.

6. Maarita vertailusaannot eksplisiittisesti:
   - Scalar-muoto on exact-vertailu.
   - Dict-muoto kayttaa annettua toleranssia: `{'value': -3.4, 'tolerance': 0.01}`.
   - Ala kayta piilotettuja suuria toleransseja.
   - Suositellut toleranssit tarvittaessa:
     - `rpnz_w`: exact tai +/- 1 W
     - `required_power_w`: exact tai +/- 1 W
     - `required_power_consumption_kw`: exact helperilla generoituna, muuten esimerkiksi +/- 0.001 kW tai eksplisiittinen toleranssi
     - `remaining_quarter_s`: exact
     - `remaining_quarter_min` / `remaining_template_minutes`: exact
     - `pv_power_kw`, jos joskus validoidaan derived-intention yhteydessa: exact tai +/- 0.001 kW

Valmis, kun:

- Uusi runner-testi todistaa scalar- ja tolerance-muodon.
- Vahintaan yksi pieni e2e-step kayttaa raw-inputteja ja `expect_derived`-lohkoa.

## Vaihe 3: tee fixture-migraatioapuri e2e-kayttoon

Tavoite: vanhat intent-arvot voidaan muuntaa raw-runtime-arvoiksi ilman kasinlaskua.

Nykyinen `tests/helpers.py::runtime_inputs_for_net_zero()` tekee jo paa-asian:

```python
quarter_energy_balance_kwh = balance_for_rpnz_w(rpnz_w, remaining_s=remaining_s)
required_power_w = required_power_consumption_kw * 1000.0
grid_power_w = -required_power_w - quarter_energy_balance_kwh * 60000.0 / remaining_min
```

Muutokset:

1. Tarkista kaavan vastaavuus tuotannon `compute_required_power_w()`-funktioon.
   - Nykyinen kaava on oikea inversio, kun `quarter_energy_balance_kwh < export_balance_stop_kwh`.
   - Toteuta stop-threshold-poikkeus kovana reunana: jos balance on >= `0.130`, tuotanto pakottaa `required_power_w = 0`.
   - Jos apurilta pyydetaan nonzero `required_power_consumption_kw` ja muodostuva `quarter_energy_balance_kwh >= 0.130`, apurin tulee failata fixture construction -virheella eika generoida hiljaa epakonsistenttia raw-inputtia.

2. Luo e2e-niminen apuri, esimerkiksi `tests/e2e_entity/net_zero_inputs.py`:
   - `balance_for_rpnz_w(rpnz_w, remaining_s)`
   - `grid_power_for_required_power_kw(required_power_consumption_kw, quarter_energy_balance_kwh, remaining_min)`
   - `runtime_inputs_for_net_zero_intent(E, rpnz_w, required_power_consumption_kw, at_s, pv_power_w=None, pv_power_kw=None)`
   - `expect_derived_for_net_zero_intent(...)`

3. Kayta `seconds_until_next_quarter(at_s)` ja `remaining_template_minutes(at_s)` tuotannon helper-funktioista.
   - Ala toteuta quarter-matematiikkaa uudelleen e2e-runneriin, paitsi jos erillinen testi nimenomaan testaa apurikaavojen ekvivalenssia.

4. Pida output Python-diktina, koska nykyiset stepit ovat Pythonia:

```python
'set': runtime_inputs_for_net_zero_intent(
    E,
    rpnz_w=-10,
    required_power_consumption_kw=-3.4,
    at_s=135,
    pv_power_kw=1.7,
),
'expect_derived': expect_derived_for_net_zero_intent(
    rpnz_w=-10,
    required_power_consumption_kw=-3.4,
    at_s=135,
),
```

Valmis, kun:

- Apureilla on unit-testit reunatapauksille.
- Apuria kayttava e2e-step todistaa, etta policy-polku kayttaa tuotannon derive-funktiota ilman legacy overridea.

## Vaihe 4: mahdollista raw-mode ilman monkey-patchia

Tavoite: samassa testisuitessa voi ajaa raw-input-steppeja tuotannon derive-funktiolla ja legacy-steppeja shimilla migration-ajaksi.

Muutokset:

1. Lisaa `QuarterScenarioHarness`-luokkaan tila, joka tietaa kaytettiinko nykyisessa stepissa legacy-intenttia.
   - Esimerkiksi `_legacy_derived_override_active`.
   - Aseta `True`, jos `_normalize_legacy_runtime_inputs()` loytaa legacy RPNZ/RPC -syotteita.
   - Aseta `False`, kun stepissa ei ole legacy-syotteita.

2. Muuta `_run_policy_loop()`:
   - Jos legacy override on aktiivinen, kayta nykyista `_derive_net_zero_inputs_for_test`.
   - Muuten palauta `self.policy_mod['derive_net_zero_inputs'] = self._real_derive_net_zero_inputs`.

3. Lisaa guard:
   - Jos stepissa on raw `grid_power_w`/`quarter_energy_balance_kwh` ja legacy RPNZ/RPC samaan aikaan, vaadi `expect_derived` tai tarkista konsistenssi.
   - Epailyttavin nykyinen muoto on se, jossa `E['grid_power_w']` on mukana mutta RPNZ/RPC tulevat legacy-shimista. Sita ei voi kieltaa heti, koska nykyiset testit kayttavat sita laajasti.

4. Ensimmainen raw-input pilotti pitaa todistaa, etta monkey-patch ei ole aktiivinen:
   - Lisaa testissa tai runnerissa tarkistus esimerkiksi `assert h._legacy_derived_override_active is False`.
   - Saanto: jos step kayttaa raw runtime -syotteita eika legacy-avaimia tai `net_zero_intent`-blokkia, harness ei saa monkey-patchata `derive_net_zero_inputs()`-funktiota.

Valmis, kun:

- Raw-stepit ajavat tuotannon derive-funktiolla.
- Legacy-stepit ajavat edelleen shimilla.
- Sekamuoto ei paase lisaantymaan uusiin migroituihin testeihin huomaamatta.

## Vaihe 5: migroi kriittiset skenaariot ensin

Migraatiojarjestys kannattaa pitaa pienen riskin ja suuren arvon mukaan.

1. EV hard-off / restore-min:
   - `tests/e2e_entity/net_zero_ev_adjustable_load/test_02_release_and_hard_off_hold.py`
   - `tests/e2e_entity/net_zero_ev_adjustable_load/test_03_post_hard_off_recovery.py`
   - `tests/e2e_entity/hard_off_on_low_pv/*`

2. HOME_BATTERY primary + EV adjustable:
   - `tests/e2e_entity/net_zero_homebattery_adjustable_load/*`
   - `tests/e2e_entity/haeo_02_net_zero_homebattery_primary_ev_adjustable/*` jos xfail-semanttiikka on edelleen tarkoituksellinen, pidetaan se erillisena.

3. RPNZ practical-zero ja surplus release:
   - `tests/e2e_entity/net_zero_priority_order_quarter/*`
   - `tests/e2e_entity/net_zero_priority_order_quarter_3_relays/*`

4. Battery import/export correction:
   - `tests/e2e_entity/net_zero_force_on_battery_support/*`
   - `tests/e2e_entity/battery_protect_min_cell_recovery/*` vain niilta osin kuin NET_ZERO-derived intent on relevantti.

Migraatiokaava yhdelle stepille:

1. Ota nykyiset legacy-arvot:
   - `E['rpnz_w']`
   - `E['required_power_consumption_kw']`
   - `E['pv_power_kw']` tai `E['pv_power_w']`
   - `at_s`
2. Laske raw runtime -arvot apurilla.
3. Korvaa setissa legacy RPNZ/RPC raw-arvoilla:
   - `E['quarter_energy_balance_kwh']`
   - `E['grid_power_w']`
   - `E['pv_power_w']`
4. Lisaa `expect_derived`.
5. Pida `expect_device_policies`, `expect_policy`, `expect_values` ja writer-odotukset ennallaan.
6. Aja kyseisen storyn testit.
7. Jos policy-odotus muuttuu, pysahdy arvioimaan: onko vanha skenaario ollut fysikaalisesti epakonsistentti vai paljastuiko regressio?
   - A: vanha fixture oli matemaattisesti epakonsistentti ja uusi raw-fixture sailyttaa tarkoitetun business-tilanteen.
   - B: business-kaytos muuttuu tarkoituksella.
   - C: vanha testiodotus oli vaarin.
   - D: tuotantobugi loytyi.

Oletus on, etta business-odotukset pidetaan ennallaan.

## Vaihe 6: kirista legacy-kayttoa

Tavoite: legacy-intent ei jaa huomaamatta pysyvaksi e2e-malliksi.

Kun kriittiset skenaariot on migroitu:

1. Lisaa `scenario_runner.py`-guard, joka vaatii legacy-steppeihin eksplisiittisen merkinnan:

```python
'legacy_net_zero_intent': True
```

2. Tai vaihtoehtoisesti muuta step-muoto selkeammaksi:

```python
'net_zero_intent': {
    'rpnz_w': 500,
    'required_power_consumption_kw': 2.6,
    'pv_power_kw': 8.0,
}
```

3. Poista hiljainen `E['rpnz_w']`/`E['required_power_consumption_kw']`-kaytto uusista testeista.

4. Lisaa `rg`-pohjainen tarkistus dokumentoituun testausohjeeseen:

```text
rg "E\\['(rpnz_w|required_power_consumption_kw|required_power_w|pv_power_kw)'\\]" tests/e2e_entity
```

5. Seuraa myos monkey-patch-viitteita:

```text
rg "derive_net_zero_inputs.*_for_test|policy_mod\\['derive_net_zero_inputs'\\]|monkeypatch.*derive_net_zero_inputs" tests/e2e_entity tests/helpers.py
```

6. Raportoi jokaisen migraatiovaiheen lopussa maara:

```text
Legacy NET_ZERO E2E direct-key count before: N
Legacy NET_ZERO E2E direct-key count after:  M
Raw-input + expect_derived pilot scenarios added: K
```

Valmis, kun:

- Jaljella oleva legacy-kaytto on listattu ja perusteltu.
- Uudet tai migroidut NET_ZERO-stepit kayttavat raw runtime + `expect_derived` -muotoa.

## Vaihe 7: poista monkey-patch

Tavoite: e2e-suite harjoittaa samaa derived-input-polku kuin tuotanto.

Edellytykset:

- Korkean arvon NET_ZERO-skenaariot ovat raw-muodossa.
- `rg` ei loyda kriittisista skenaarioista legacy RPNZ/RPC -syotteita.
- Legacy-intentille ei ole enaa business-kriittista riippuvuutta.

Muutokset:

1. Poista `QuarterScenarioHarness._derive_net_zero_inputs_for_test()`.
2. Poista `_legacy_required_power_w` ja `_legacy_rpnz_w`.
3. Poista `self.policy_mod['derive_net_zero_inputs'] = self._derive_net_zero_inputs_for_test`.
4. Poista legacy-aliakset `h.ent`-kartasta tai jata ne hetkeksi virhetta nostaviksi avaimiksi.
5. Paivita testit, jotka viela kayttavat legacy-avaimia.

Valmis, kun:

- Koko e2e-suite ajaa tuotannon `derive_net_zero_inputs()`-funktiolla.
- `expect_derived` varmistaa fixtureiden intention.
- Legacy runtime -kentat eivat palaa e2e-skenaarioihin.

## Testausstrategia

Minimit jokaisessa vaiheessa:

```text
./run_pytest.sh tests/unit/test_net_zero_derived_inputs.py
./run_pytest.sh tests/contract/test_grouped_config_runtime_parity.py
```

Kun runneria tai harnessia muutetaan:

```text
./run_pytest.sh tests/e2e_entity/net_zero_ev_adjustable_load
./run_pytest.sh tests/e2e_entity/net_zero_priority_order_quarter
```

Kun migraatio etenee laajemmin:

```text
./run_pytest.sh tests/e2e_entity
```

Lisaksi tarkista legacy-kayton maara ennen ja jalkeen:

```text
rg "E\\['(rpnz_w|required_power_consumption_kw|required_power_w|pv_power_kw)'\\]" tests/e2e_entity | wc -l
rg "derive_net_zero_inputs.*_for_test|policy_mod\\['derive_net_zero_inputs'\\]|monkeypatch.*derive_net_zero_inputs" tests/e2e_entity tests/helpers.py
```

## Riskit ja hallinta

- Riski: raw-inputteihin siirto muuttaa policy-odotuksia.
  - Hallinta: migroi yksi story kerrallaan ja pida policy-odotukset ensin muuttumattomina.

- Riski: legacy `grid_power_w` ja legacy RPNZ/RPC ovat nykytesteissa epakonsistentteja.
  - Hallinta: `expect_derived` kertoo fixture-virheena, mika arvo ei vastaa tuotannon derive-kaavaa.

- Riski: quarter time -logiikka aiheuttaa yllattavia eroja.
  - Hallinta: apurit kayttavat samoja `seconds_until_next_quarter()` ja `remaining_template_minutes()` -funktioita kuin tuotanto.

- Riski: `pv_power_kw` vs `pv_power_w` sekoittuu migraatiossa.
  - Hallinta: lopullisessa raw-muodossa kaytetaan vain `pv_power_w`; apuri voi ottaa migration-mukavuussyotteena `pv_power_kw`.

## Seuraavan session ensimmainen konkreettinen tehtava

Aloita vaiheesta 2 ja pienesta pilotista:

1. Toteuta `expect_derived`-assertiot `tests/e2e_entity/scenario_runner.py`-tiedostoon.
2. Toteuta `expect_derived` niin, etta se lukee efektiivisen harness-tilan stepin jalkeen ja kutsuu tuotannon `derive_net_zero_inputs()`-funktiota.
3. Lisaa e2e-apuri raw input -arvojen muodostamiseen, mieluiten uuteen `tests/e2e_entity/net_zero_inputs.py`-tiedostoon.
4. Varmista, etta raw-mode-step ei aktivoi legacy monkey-patchia.
5. Migroi yksi step tiedostosta `tests/e2e_entity/net_zero_ev_adjustable_load/test_02_release_and_hard_off_hold.py`.
6. Mittaa legacy-kaytto ennen ja jalkeen.
7. Aja kohdennetut testit:

```text
./run_pytest.sh tests/unit/test_net_zero_derived_inputs.py
./run_pytest.sh tests/e2e_entity/net_zero_ev_adjustable_load/test_02_release_and_hard_off_hold.py
```

Jos pilotti menee lapi ilman odotusarvomuutoksia, jatka saman storyn loput stepit samalla kaavalla.

## Hyvaksymiskriteerit review-tarkennusten jalkeen

Functional:

- E2E runner tukee `expect_derived`-lohkoa.
- `expect_derived` lukee efektiivisen harness-tilan stepin jalkeen.
- `expect_derived` kutsuu tuotannon `derive_net_zero_inputs()`-funktiota.
- Raw-input-stepit voivat ajaa ilman `derive_net_zero_inputs()` monkey-patchia.
- Legacy-stepit voivat viela ajaa migration-aikana.
- Vahintaan yksi kriittinen E2E-step on migroitu raw input + `expect_derived` -muotoon.

Safety:

- Ei laajoja odotusarvorewriteja.
- Jokainen odotusarvomuutos luokitellaan A-D-listan mukaan.
- Legacy RPNZ/RPC direct-key -maara lasketaan ja raportoidaan.
- `pv_power_kw` ei ole lopullinen raw-input; lopullinen muoto kayttaa aina `pv_power_w`.
