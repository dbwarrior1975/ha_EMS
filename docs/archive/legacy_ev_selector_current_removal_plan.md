# Legacy EV selector current -poistosuunnitelma

## Toteutustila 2026-06-28

Vaiheet 1-4 on toteutettu.

Tehdyt muutokset:

1. `modules/ems_core/integrations/haeo_horizon.py`
   - poistettu `ev_power_w_to_selector_current_a`-importti
   - poistettu `ev_kw_to_selector_current_a`
   - forecast-apufunktiot `_to_ts` ja `latest_forecast_value_at_or_before` sailyvat
2. `modules/ems_core/domain/ev_power.py`
   - poistettu legacy-funktio `ev_power_w_to_selector_current_a`
   - wattipohjainen `ev_power_w_to_current_a`-polku sailyy
3. `tests/unit/test_haeo_horizon.py`
   - poistettu legacy-wrapperin importti ja sita koskeneet testit
   - forecast-testit sailyvat
4. `tests/unit/test_ev_power.py`
   - poistettu selector current -legacytestit
   - wattipohjaiset domain-testit sailyvat
5. `docs/dev/arkkitehtuuri.md`
   - tarkennettu, etta `haeo_horizon.py` tekee vain forecast-poiminnan
6. `docs/dev/testausautomaatio.md`
   - paivitetty HAEO-testikattavuuden kuvaus vastaamaan uutta vastuujakoa

Varmistus:

1. `pytest -q tests/unit/test_ev_power.py tests/unit/test_haeo_horizon.py`
   - tulos: `16 passed`
2. `rg -n "ev_power_w_to_selector_current_a|ev_kw_to_selector_current_a" modules tests ems_policy_engine.py docs/dev`
   - tulos: ei aktiivisia osumia

Jaljelle jaa vain historiallisia mainintoja taman dokumentin lisaksi arkistodokumenteissa, joita ei paivitetty osana tata muutosta.

## Tausta

Katselmointipalautteen kohde on legacy-polku, joka muuntaa EV-tehon vanhaan selector-virta-arvoon:

1. `modules/ems_core/domain/ev_power.py`: `ev_power_w_to_selector_current_a`
2. `modules/ems_core/integrations/haeo_horizon.py`: `ev_kw_to_selector_current_a`

Nykyinen wattipohjainen ydinputki käyttää `ev_power_w_to_current_a`-funktiota ja EV-laitteen kyvykkyyksia (`min_absorb_w`, `max_absorb_w`, `power_step_w`, `current_step_a`, `phases`, `voltage_v`). Legacy-selector-polku kiertaa osan tasta mallista kayttamalla suoraan `min_a`, `max_a` ja `step_a` -parametreja.

## Nykyiset viittaukset

Tuotantokoodi:

1. `modules/ems_core/domain/ev_power.py`
   - maarittelee `ev_power_w_to_selector_current_a`
2. `modules/ems_core/integrations/haeo_horizon.py`
   - importoi `ev_power_w_to_selector_current_a`
   - maarittelee wrapperin `ev_kw_to_selector_current_a`
3. `ems_policy_engine.py`
   - kayttaa `haeo_horizon`-moduulista vain `latest_forecast_value_at_or_before`-funktiota

Testit:

1. `tests/unit/test_ev_power.py`
   - testaa suoraan `ev_power_w_to_selector_current_a`-funktiota
2. `tests/unit/test_haeo_horizon.py`
   - importoi ja testaa `ev_kw_to_selector_current_a`-wrapperia
   - samassa tiedostossa on myos HAEO-forecast-parsinnan testit, jotka tulee sailyttaa

Dokumentaatio:

1. `docs/dev/arkkitehtuuri.md`
   - kuvaa HAEO:n roolia ja viittaa `haeo_horizon.py`-tiedostoon
2. `docs/dev/testausautomaatio.md`
   - kuvaa `test_haeo_horizon.py`-testikattavuutta
3. Arkistodokumenteissa voi olla historiallisia mainintoja. Niita ei tarvitse muuttaa, ellei tavoitteena ole poistaa kaikki tekstiosumat koko reposta.

## Tavoitetila

Tavoitetilassa `haeo_horizon.py` vastaa vain HAEO-forecastin aikaleima- ja arvoparsinnasta. Se ei sisalla EV-tehosta selector-virtaan tehtavaa legacy-muunnosta.

`ev_power.py` sisaltaa vain wattipohjaisen EV-domain-logiikan ja tarvittavat virta-teho-apufunktiot. Selector-nykyarvon legacy-muunnos poistetaan tai eristetaan selkeasti arkistoituun compatibility-paikkaan.

## Suositeltu toteutus: poisto

### 1. Poista HAEO-wrapper

Muuta `modules/ems_core/integrations/haeo_horizon.py`:

1. poista importti `from ems_core.domain.ev_power import ev_power_w_to_selector_current_a`
2. poista funktio `ev_kw_to_selector_current_a`
3. jata `_to_ts` ja `latest_forecast_value_at_or_before` ennalleen

Perustelu: nykyinen policy engine lukee HAEO EV-targetin kilowatteina (`ev_target_kw`) ja varsinainen EV-ohjaus kuuluu wattipohjaiseen ydinputkeen, ei HAEO-integraation selector-muunnokseen.

### 2. Poista domainin legacy-funktio

Muuta `modules/ems_core/domain/ev_power.py`:

1. poista `ev_power_w_to_selector_current_a`
2. varmista, etta `ev_power_w_to_current_a` ja muut wattipohjaiset apufunktiot jaavat ennalleen

Perustelu: `ev_power_w_to_current_a` kayttaa laitekyvykkyyksiin perustuvia wattirajoja ja nykyista kvantisointimallia. Legacy-funktio rakentaa erillisen selector-kandidaattilistan, joka voi poiketa uuden mallin rajoista.

### 3. Paivita unit-testit

Muuta `tests/unit/test_haeo_horizon.py`:

1. poista `ev_kw_to_selector_current_a` importista
2. poista kaikki `test_ev_kw_to_selector_current_a_*` -testit
3. sailyta forecast-parsinnan testit

Muuta `tests/unit/test_ev_power.py`:

1. poista `test_ev_power_to_selector_current_*` -testit
2. varmista, etta `ev_power_w_to_current_a` kattaa edelleen oleelliset rajatapaukset:
   - ei ylita maksimiwattirajasta johdettua virtaa
   - hylkaa rajoihin nahden esityskelvottoman askelkoon
   - kvantisoi nykyisen `current_step_a`-mallin mukaan

### 4. Paivita dokumentaatio

Muuta `docs/dev/arkkitehtuuri.md`:

1. tarkenna HAEO:n rooli: `haeo_horizon.py` tekee vain forecast-arvon poiminnan
2. poista tai valta tulkinta, etta HAEO-integraatio muuntaa EV-targetin selector-virraksi

Muuta `docs/dev/testausautomaatio.md`:

1. paivita HAEO-testikattavuuden kuvaus koskemaan vain forecast-parsintaa
2. mainitse EV-teho/virta-kvantisoinnin kattavuus `test_ev_power.py`-testien yhteydessa, jos dokumenttiin halutaan erillinen EV-domain-osio

## Vaihtoehto: legacy-eristys poistamisen sijaan

Jos tarvitaan lyhyt siirtymakausi, siirra legacy-funktiot erilliseen compatibility-moduuliin:

1. uusi moduuli esimerkiksi `modules/ems_core/integrations/legacy_ev_selector.py`
2. siirra `ev_power_w_to_selector_current_a` ja `ev_kw_to_selector_current_a` sinne
3. merkitse moduuli docstringilla deprecated/legacy-kayttoon
4. varmista, ettei tuotantokoodi importoi moduulia
5. siirra tai poista testit sen mukaan, halutaanko legacy-kayttaytyminen viela lukita

Tata vaihtoehtoa kannattaa kayttaa vain, jos ulkoinen kayttaja tai julkaistu API tarvitsee funktioita viela. Muuten suora poisto on selkeampi ja vahentaa yllapidettavaa logiikkaa.

## Regressioriskit

1. Testit voivat edelleen importoida poistettuja funktioita, jolloin pytest kaatuu kerailyvaiheessa.
2. Jos jokin ulkoinen skripti kayttaa `ev_kw_to_selector_current_a`-funktiota suoraan, se rikkoutuu. Repon sisaisista osumista tuotantokayttoa ei nay.
3. EV-ohjauksen numeerinen kayttaytyminen ei muutu, jos poistetaan vain kayttamaton legacy-polku. Muutos on silti varmistettava EV-domain- ja HAEO-testien kautta.

## Tarkistuslista toteutukselle

1. Aja tekstihaku ennen muutosta:
   - `rg -n "ev_power_w_to_selector_current_a|ev_kw_to_selector_current_a"`
2. Tee koodipoistot `haeo_horizon.py`- ja `ev_power.py`-tiedostoihin.
3. Paivita testit poistamalla legacy-selector-testit ja sailyttamalla forecast-testit.
4. Paivita kehittajadokumentaatio.
5. Aja kohdennetut testit:
   - `pytest -q tests/unit/test_ev_power.py tests/unit/test_haeo_horizon.py`
6. Aja tarvittaessa laajempi regressio:
   - `pytest -q`
7. Varmista lopuksi, ettei aktiivisessa koodissa ole legacy-osumia:
   - `rg -n "ev_power_w_to_selector_current_a|ev_kw_to_selector_current_a" modules tests ems_policy_engine.py`

## Hyvaksyntakriteerit

1. `ev_power_w_to_selector_current_a` ei ole enaa aktiivisessa domain-koodissa.
2. `ev_kw_to_selector_current_a` ei ole enaa `haeo_horizon.py`-moduulissa.
3. HAEO-forecastin testit menevat edelleen lapi.
4. EV-domainin wattipohjaiset testit menevat edelleen lapi.
5. Repon aktiivisessa tuotanto- ja testikoodissa ei ole importteja poistettuihin legacy-funktioihin.
