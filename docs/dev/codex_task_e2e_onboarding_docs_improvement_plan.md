# E2E onboarding docs improvement plan

Päiväys: 2026-07-01

## Tausta

Palautedokumentti `docs/dev/codex_review_notes_e2e_onboarding_docs.md`
arvioi, että nykyinen E2E-automaatio on teknisesti vahva, mutta NET_ZERO
-fixtureiden merkintätapa ei ole riittävän itseään selittävä uudelle
kehittäjälle.

Keskeinen riski on oikea: testikoodi näyttää edelleen käyttävän arvoja
`rpnz_w` ja `required_power_consumption_kw` skenaarion `set`-osassa, vaikka
tuotanto-EMS lukee raakana runtime-syötteenä muun muassa:

1. `grid_power_w`
2. `quarter_energy_balance_kwh`
3. `pv_power_w`

Nykyinen `tests/e2e_entity/net_zero_inputs.py` tukee palautteen pääväitettä:
`runtime_inputs_for_net_zero_intent()` palauttaa raw runtime entity -arvoja,
mutta funktiolla ei ole docstringiä. Uusi kehittäjä voi siksi helposti tulkita
helperin argumentit tuotannon runtime-inputeiksi eikä fixture intentiksi.

## Arvio palautteen perusteltavuudesta

### Perusteltu

1. `runtime_inputs_for_net_zero_intent()` ja
   `expect_derived_for_net_zero_intent()` tarvitsevat selkeät docstringit.
   Nykyinen tiedosto ei selitä, että RPNZ/RPC ovat haluttu johdettu
   liiketoimintatilanne eivätkä EMS:lle syötettäviä runtime-entiteettejä.
2. Erillinen NET_ZERO fixture -konventiodokumentti on perusteltu. Nykyinen
   `tests/e2e_entity/e2e_conventions.md` kuvaa kanonisen E2E-sopimuksen, mutta
   ei selitä raw-input-fixtureiden ja `expect_derived`-assertion suhdetta.
3. Olemassa oleviin E2E-dokumentteihin kannattaa lisätä lyhyt linkki uuteen
   fixture-konventioon. Muuten uusi dokumentti jää helposti piiloon.
4. Dokumentaatiossa on tarkistettavia stale-kohtia:
   `docs/dev/testausautomaatio.md` viittaa edelleen `tests/scenarios/`
   -hakemistoon toissijaisena testipintana, ja sekä `testausautomaatio.md`
   että `docs/dev/e2e_tests_stories.md` väittävät `scenario_overview.md`
   -tiedostojen olevan story-kansioissa. Nykyisestä puusta niitä ei löydy.
5. `README.md`:ssä on yhä aktiiviselta näyttäviä
   `sensor.ems_policy_decision_trace_pyscript`- ja `policy_decision_trace`
   -viitteitä. Ne pitää arvioida erikseen suhteessa nykyiseen canonical
   device-policy / dispatch-command -pintaan.

### Osittain perusteltu

1. Helperin rename tai alias on hyödyllinen, mutta ei välttämätön ensimmäiseen
   korjausvaiheeseen. Vahvat docstringit ja konventiodokumentti ratkaisevat
   suurimman onboarding-riskin pienemmällä muutoksella.
2. Scenario notejen massapäivitystä ei kannata tehdä yhdellä laajalla sweepillä.
   Parempi on päivittää vain uudet tai muuten kosketetut NET_ZERO-askeleet
   tyyliin `intent: RPNZ=..., RPC=..., PV=...`.
3. Erillinen migration status -dokumentti voi olla hyödyllinen, mutta sen voi
   toteuttaa myös uuden fixture-konventiodokumentin lyhyenä osiona, jos
   tavoite on pitää dokumentaatio kevyenä.

### Ei ensisijainen tässä työssä

1. E2E-runnerin redesign ei ole tarpeen.
2. NET_ZERO-bisneslogiikkaa tai policy-/writer-odotusarvoja ei pidä muuttaa
   dokumentaatioparannuksen yhteydessä.
3. Kaikkien skenaarioiden mekaaninen migraatio tai notejen massakorjaus
   kasvattaisi riskiä ilman välitöntä hyötyä.

## Tavoitetila

Uuden kehittäjän pitää pystyä vastaamaan dokumentaation perusteella:

1. Mitä raw NET_ZERO runtime -syötteitä tuotanto-EMS lukee?
2. Miksi E2E-testit mainitsevat edelleen RPNZ/RPC-arvoja?
3. Mitä `runtime_inputs_for_net_zero_intent()` palauttaa?
4. Mitä `expect_derived_for_net_zero_intent()` validoi?
5. Miten uusi NET_ZERO E2E-step kirjoitetaan turvallisesti?
6. Miten fixture-virhe erotetaan policy-regressiosta?
7. Mitkä arvot ovat watteja ja mitkä kilowatteja?
8. Mitä ei saa muuttaa vain siksi, että raw-input-migraatio menee läpi?

## Suunnitelma

### Vaihe 1: Helperien docstringit

Päivitä `tests/e2e_entity/net_zero_inputs.py`.

Lisää `runtime_inputs_for_net_zero_intent()`-funktiolle docstring, joka kertoo:

1. funktio rakentaa production-equivalent raw EMS runtime inputit
2. funktio ei syötä `rpnz_w`- tai `required_power_consumption_kw`-arvoja EMS:lle
3. palautus sisältää `quarter_energy_balance_kwh`, `grid_power_w` ja
   valinnaisesti `pv_power_w`
4. RPNZ/RPC-argumentit kuvaavat haluttua johdettua business intentiä
5. pariksi kuuluva `expect_derived` varmistaa, että tuotannon
   `derive_net_zero_inputs()` johtaa samat arvot raw-syötteistä

Lisää `expect_derived_for_net_zero_intent()`-funktiolle docstring, joka kertoo:

1. funktio rakentaa odotetut johdetut NET_ZERO-arvot fixture intentille
2. runner vertaa näitä tuotannon `derive_net_zero_inputs()`-funktion tulokseen
3. epäonnistuminen viittaa ensisijaisesti fixture-rakennusvirheeseen, ei heti
   policy-regressioon

Älä muuta tässä vaiheessa helperien laskentaa tai testien odotusarvoja.

### Vaihe 2: NET_ZERO fixture -konventiodokumentti

Luo `tests/e2e_entity/net_zero_fixture_conventions.md`.

Minimirakenne:

1. One-minute summary
2. Production runtime contract
3. Why RPNZ/RPC still appear in tests
4. What `runtime_inputs_for_net_zero_intent()` returns
5. What `expect_derived` validates
6. Example with helper
7. Same example without helper
8. Fixture error vs policy regression
9. What not to do
10. Migration-status caveat

Dokumenttiin pitää kirjata eksplisiittisesti tämä malli:

```text
RPNZ/RPC shown in helper arguments
    -> fixture helper calculates raw EMS inputs
    -> h.step() applies quarter_energy_balance_kwh, grid_power_w, pv_power_w
    -> EMS production code derives RPNZ/RPC internally
    -> expect_derived verifies fixture intent
    -> policy / dispatch / writer expectations are checked
```

Dokumentissa pitää olla myös raw-input-esimerkki ilman helperiä, jotta lukija
näkee mitä helper piilottaa.

### Vaihe 3: Linkitä nykyisiin E2E-dokumentteihin

Päivitä vähintään:

1. `tests/e2e_entity/e2e_conventions.md`
2. `docs/dev/testausautomaatio.md`
3. `docs/dev/e2e_tests_stories.md`
4. `docs/dev/README.md`

Lisää lyhyt viite:

```markdown
NET_ZERO raw runtime fixtureiden ja `expect_derived`-käytännön kuvaus:
`tests/e2e_entity/net_zero_fixture_conventions.md`.
```

Pidä muutos lyhyenä. Älä tee laajaa dokumentaatiouudelleenkirjoitusta tässä
vaiheessa.

### Vaihe 4: Korjaa selvästi stale E2E-onboarding-viitteet

Korjaa samalla passilla dokumentaatiokohdat, jotka vaikuttavat suoraan
E2E-onboardingiin:

1. `scenario_overview.md`-väite pitää poistaa tai muuttaa muotoon, jossa
   nykyinen dokumentaatiorakenne ei lupaa olemattomia tiedostoja.
2. `tests/scenarios/` pitää kuvata historiallisena tai toissijaisena vain, jos
   se on yhä oikeasti relevantti. Kanoninen E2E-pinta on
   `tests/e2e_entity/`.
3. `run_pytest.sh`-viite ei ole tällä hetkellä itsessään stale, koska tiedosto
   on olemassa. Dokumentissa pitää kuitenkin suosia samaa komentoa kuin
   projektissa oikeasti käytetään.
4. `policy_decision_trace`-viitteet pitää luokitella: aktiivinen canonical
   surface, diagnostiikkapeili, historiallinen suunnitelma tai poistettava
   stale-ohje. Älä poista historiallisia suunnitelmadokumentteja sokkona.

### Vaihe 5: Lisää ei-rikkova alias vain jos hyöty on selvä

Harkitse alias:

```python
raw_runtime_inputs_for_derived_net_zero = runtime_inputs_for_net_zero_intent
```

Tee tämä vain, jos dokumentaatiossa halutaan käyttää selvästi kuvaavampaa nimeä
uusissa esimerkeissä. Älä tee laajaa mekaanista renameä nykyisiin testeihin
samassa muutoksessa.

### Vaihe 6: Päivitä yksittäisiä scenario noteja vain kosketetuissa testeissä

Jos jokin NET_ZERO-skenaario avataan tämän työn yhteydessä, päivitä sen note
alkamaan eksplisiittisellä intentillä:

```python
'note': (
    't120 intent: RPNZ=11 W, RPC=-6.4 kW, PV=1.4 kW. '
    'Weak PV cannot cover the deficit, so EV stays pinned at burn current.'
),
```

Älä massamuokkaa kaikkia skenaarioita.

## Hyväksymiskriteerit

1. `runtime_inputs_for_net_zero_intent()` dokumentoi selvästi, että se palauttaa
   raw EMS inputit eikä syötä RPNZ/RPC-arvoja tuotantoon.
2. `expect_derived_for_net_zero_intent()` dokumentoi fixture intent
   -validoinnin.
3. `tests/e2e_entity/net_zero_fixture_conventions.md` on olemassa ja sisältää
   helper-esimerkin sekä raw-input-esimerkin.
4. Nykyiset E2E-dokumentit linkittävät uuteen konventiodokumenttiin.
5. Selvästi väärä `scenario_overview.md`-väite on korjattu tai poistettu.
6. `tests/scenarios/`-viittaus ei esiinny ensisijaisena E2E-pintana.
7. Dokumentaatiomuutos ei muuta policy-, dispatch- tai writer-odotusarvoja.
8. Uusia suoria runtime-käyttöjä avaimille `rpnz_w`,
   `required_power_consumption_kw`, `required_power_w` tai `pv_power_kw` ei
   lisätä E2E-steppeihin.

## Tarkistuskomennot

Suorat legacy runtime entity -käytöt E2E-steppeissä:

```bash
rg "E\['(rpnz_w|required_power_consumption_kw|required_power_w|pv_power_kw)'\]" tests/e2e_entity
```

Odotus: ei osumia skenaarioiden runtime `set` -pinnoista. Nykyiset
`__legacy__.*`-osumat `scenario_harness.py`:ssä ovat migration bridge, eivät
uusi käyttötapa.

NET_ZERO fixture -helperien löydettävyys:

```bash
rg "runtime_inputs_for_net_zero_intent|expect_derived_for_net_zero_intent|raw_runtime_inputs_for_derived_net_zero" tests docs
```

Stale decision trace -viitteet aktiivisessa dokumentaatiossa:

```bash
rg "sensor\.ems_policy_decision_trace_pyscript|policy_decision_trace" README.md docs tests -g '*.md' -g '!docs/archive/**' -g '!docs/dev/Downloads/**'
```

Testit dokumentaatio- ja docstring-muutoksen jälkeen:

```bash
pytest -q tests/unit/test_net_zero_derived_inputs.py
pytest -q tests/e2e_entity
pytest -q
```

Jos projektin standardiksi halutaan wrapper, käytä vastaavia
`./run_pytest.sh ...` -komentoja ja päivitä dokumentaatio sen mukaiseksi.

## Rajaukset

1. Ei E2E-runnerin redesignia.
2. Ei NET_ZERO-bisneslogiikan muutoksia.
3. Ei policy-/writer-odotusarvojen muutoksia ilman erillistä perustelua.
4. Ei kaikkien skenaarioiden massamigraatiota.
5. Ei legacy shimien poistoa tässä dokumentaatiotyössä.
6. Ei uutta YAML-skenaarioformaattia.
