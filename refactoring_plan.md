# EMS refactoring plan

Taman dokumentin tavoite on kuvata etenemisjarjestys, jolla EMS voidaan vieda kohti
yhteista laitemallia ja watteihin perustuvaa core-logiikkaa ilman isoa kertamuutosta.

Lahtokohtana ovat nykyinen toteutus, `HAEO_in_EMS.md`,
`EMSs_common_parameters.md` ja `example_EMS_config.yaml`.

## Tavoitetila

EMS core kasittelee ohjattavia laitteita yhteismitallisesti:

- tehot ja rajat ovat coren sisalla watteina
- EV:n ampeerit ovat adapteri- tai writer-tason yksityiskohta
- akku, EV ja relekuormat voidaan kuvata samalla device-mallilla
- HAEO voi tuottaa laitekohtaisia tehorajoja ja toiveita ilman kovakoodattuja
  akku/EV-haaroja
- vanha Home Assistant entity -rajapinta voidaan sailyttaa migration ajaksi

Tavoite ei ole poistaa kaikkea vanhaa entity-map-rakennetta ensimmaisessa vaiheessa.
Ensimmainen arvo syntyy siita, etta uusi malli voidaan rakentaa nykyisen rinnalle ja
todentaa testeilla ilman kayttaytymismuutosta.

## Periaatteet

1. Ei big bang -refaktorointia.
   Jokainen vaihe pitaa saada testattavaan tilaan erikseen.

2. Core puhuu watteja.
   Jos laite tarvitsee ampeereja, prosentteja, releen boolean-arvoja tai muuta
   laitekohtaista muotoa, muunnos tehdaan mahdollisimman lahella writer-tasoa.

3. Uusi device-malli tulee ensin read-modeliksi.
   Ensin rakennetaan nykyisista entityista uusi sisainen mallinnus, mutta policy
   tuottaa viela nykyiset outputit. Vasta myohemmin outputit muutetaan
   device-pohjaisiksi.

4. Trace parity on pakollinen.
   Jokaisessa vaiheessa pitaa pystyta vertaamaan vanhaa ja uutta tulkintaa
   diagnostiikassa tai testeissa.

5. HAEO NET_ZERO pysyy toimivana koko muutoksen ajan.
   Nykyinen vartin vaihteessa tapahtuva combo-valinta ja combo-change hygiene ovat
   kriittisia kayttaytymisen osia.

## Vaihe 0: baseline lukkoon

Tarkoitus: varmistaa, etta tiedamme tarkasti mita nykyinen EMS tekee ennen muutoksia.

Toimenpiteet:

- aja koko testisetti ja kirjaa baseline
- varmista, etta nykyiset HAEO e2e -testit kuvaavat halutut semantiikat
- sailyta nykyiset trace-attribuutit, vaikka uusi malli lisaantyy rinnalle
- dokumentoi mahdolliset tunnetut puutteet, joita ei korjata viela

Hyvaksynta:

- `pytest -q tests` menee lapi ennen varsinaisia refaktorointivaiheita
- nykyiset HAEO NET_ZERO ja CHEAP_GRID_CHARGE -testit ovat edelleen mukana

## Vaihe 1: sisainen device read-model

Tarkoitus: luoda uusi yhteinen malli nykyisten entityjen paalle ilman
kayttaytymismuutosta.

Lisattavat mallit:

- `EmsDeviceConfig`
- `EmsDeviceState`
- `DevicePolicy`
- mahdollisesti `DeviceRoleConstraints`

Esimerkkikenttia:

```python
EmsDeviceConfig(
    device_id="EV_CHARGER",
    kind="ev_charger",
    can_import=True,
    can_export=False,
    controllable_power=True,
    min_power_w=920,
    max_power_w=11000,
    power_step_w=920,
)
```

Toimenpiteet:

- rakenna mapperi nykyisesta `ENT`-pohjaisesta snapshotista uuteen device-malliin
- ala muuta policy-paattelya viela
- lisaa unit-testit mapperille: akku, EV, relay1 ja relay2
- lisaa traceen vapaaehtoinen debug-nakyma device-mallista, jos se ei sotke
  nykyisia tulosteita

Hyvaksynta:

- kaikki nykyiset testit menevat lapi
- uusi malli voidaan muodostaa nykyisesta entity snapshotista
- mapper ei muuta actuator- tai policy-outputteja

## Vaihe 2: EV:n W-normalisointi

Tarkoitus: poistaa coren sisainen riippuvuus EV:n ampeeriajattelusta asteittain.

Nykyinen ongelma:

- akku ohjataan watteina
- EV:n osa parametreista ja rajoista on ampeereina
- HAEO NET_ZERO joutuu jo nyt tuottamaan seka `ev_limit_w` etta `ev_limit_a`

Toimenpiteet:

- lisa sisaiset arvot:
  - `ev_min_power_w`
  - `ev_max_power_w`
  - `ev_power_step_w`
  - `ev_target_w`
  - `ev_limit_w`
- siirra W -> A -muunnos writer-adapterin lahelle
- sailyta nykyiset EV current -outputit migration ajan
- pida nykyinen `ev_kw_to_selector_current_a` yhteensopivana, mutta rajaa sen rooli
  adapterimuunnokseksi

Hyvaksynta:

- EV:n policy-paattely voidaan testata watteina
- nykyinen Home Assistantille meneva current-arvo pysyy samana
- step-arvon vaikutus on yksiselitteisesti testattu, erityisesti `step_a=1` ja
  `step_a=4`

## Vaihe 3: HAEO plan device-pohjaiseksi

Tarkoitus: muuttaa HAEO NET_ZERO -plan niin, etta se palauttaa laitekohtaisia
tehorajoja ja rooleja.

Nykyinen muoto on kaytannollinen mutta viela liian domain-spesifi:

- `primary_load`
- `adjustable_surplus_load`
- `battery_limit_w`
- `ev_limit_w`
- `ev_limit_a`

Uusi sisainen muoto:

```python
HaeoNetZeroPlan(
    active=True,
    quarter_key="...",
    primary_device_id="EV_CHARGER",
    adjustable_device_id="HOME_BATTERY",
    device_limits_w={
        "EV_CHARGER": 5000,
        "HOME_BATTERY": 1000,
    },
    changed=True,
)
```

Toimenpiteet:

- lisa device-pohjainen plan-muoto nykyisen rinnalle
- sailyta legacy-attribuutit traceissa ja testeissa migration ajan
- muuta combo-valinta kayttamaan device-id:ta sisaisesti
- pida nykyiset helper-arvot read-only -luonteisina, kun HAEO plan on aktiivinen

Hyvaksynta:

- nykyiset HAEO NET_ZERO e2e -testit menevat lapi
- quarter change ja combo change hygiene toimivat device-id-pohjaisesti
- legacy trace kertoo edelleen vanhat arvot, jotta kayttaja ei meneta nakyvyytta

## Vaihe 4: surplus-allokointi device-malliin

Tarkoitus: irrottaa surplus-ohjaus kovakoodatuista EV/relay/battery-haaroista.

Uusi ajatus:

- jokaisella surplus-kelpoisella laitteella on:
  - `activation_threshold_w`
  - `min_power_w`
  - `max_power_w`
  - `power_step_w`
  - `can_absorb_surplus`
  - `response_kind`: continuous, selector, relay
- policy valitsee tavoitetehon laitteelle
- adapteri muuttaa tavoitteen laitteen tarvitsemaksi ohjaukseksi

Toimenpiteet:

- mallinna nykyiset EV adjustable, relay1 ja relay2 samaan surplus-device-listaan
- tee ensin rinnakkainen laskenta traceen
- vertaa vanhan ja uuden surplus-paattelyn tuloksia testeissa
- muuta policy kayttamaan uutta allokaattoria vasta, kun parity on hyva

Hyvaksynta:

- nykyinen surplus-kayttaytyminen ei muutu ilman tarkoituksellista testimuutosta
- HAEO combo-change clear/freeze toimii myos device-pohjaisilla rooleilla
- releiden boolean-ohjaus syntyy adapterissa device targetin perusteella

## Vaihe 5: policy output device-pohjaiseksi

Tarkoitus: muuttaa policy-output sisaisesti laitekohtaiseksi, mutta jatkaa vanhan HA
entityrajapinnan tukemista.

Uusi sisainen output:

```python
DevicePolicy(
    device_id="EV_CHARGER",
    target_power_w=3680,
    enabled=True,
    reason="HAEO_NET_ZERO_ADJUSTABLE",
)
```

Toimenpiteet:

- tuota ensin device-policy ja vanhat actuator-arvot rinnakkain
- muuta writer lukemaan device-policya
- pida vanhat actuator entityt julkaistuina, kunnes migration on valmis
- lisaa testeja, joissa sama target tuottaa eri writer-outputin eri laitekonfiguraatiolla

Hyvaksynta:

- policy-testeissa paatulos voidaan validoida watteina
- Home Assistant -outputit pysyvat yhteensopivina
- EV:n ampeerit eivat vuoda core-paattelyyn

## Vaihe 6: uusi konfiguraatiorakenne

Tarkoitus: ottaa kayttoon `example_EMS_config.yaml`-tyylinen ryhmitelty
parametrointi.

Toimenpiteet:

- tee loader uudelle konfiguraatiolle
- tee adapteri, joka pystyy rakentamaan saman device-mallin vanhasta entity-mapista ja
  uudesta config-rakenteesta
- tue dual-read-vaihetta:
  - vanha entity-map on oletus
  - uusi config voidaan ottaa kayttoon kokeellisesti
- lisaa validaatio:
  - pakolliset device-id:t
  - min/max/step ovat johdonmukaisia
  - role constraintit ovat mahdollisia
  - HAEO:n tuottamat device-id:t loytyvat konfiguraatiosta

Hyvaksynta:

- esimerkkikonfiguraatio validoituu automaatiolla
- vanha konfiguraatiotapa toimii edelleen
- uusi config tuottaa saman sisaisen device-mallin kuin vanha asetuskanta

## Vaihe 7: vanhan toiston poisto

Tarkoitus: poistaa vanhan entity-mapin semanttinen toisto vasta, kun uusi malli on
todistanut toimivuutensa.

Poistettavia tai yhdistettavia asioita:

- akkuun sidottu `floor`-terminologia, jos kyse on yleisesta min/max/guard-rajasta
- EV:n ampeeriparametrit core-paattelyn tasolta
- erilliset laitekohtaiset policy-haarat silloin, kun yhteinen device-policy riittaa
- rinnakkaiset legacy trace -kentat, jos kayttajilla on korvaava diagnostiikka

Hyvaksynta:

- migration-polku on dokumentoitu
- release note kertoo poistuvat entityt tai muuttuneet merkitykset
- vanhat testit on joko sailytetty yhteensopivuustesteina tai korvattu
  device-pohjaisilla testeilla

## Testausstrategia

Jokaisessa vaiheessa tarvitaan kolme testitasoa:

1. Mapper/unit-testit
   Todistavat, etta entity snapshot, config ja device-malli vastaavat toisiaan.

2. Policy-testit
   Todistavat, etta watteihin perustuva paattely tuottaa oikean device targetin.

3. E2E entity -testit
   Todistavat, etta Home Assistantille nakyvat actuatorit eivat muutu vahingossa.

Erityisen tarkeita regressiotesteja:

- HAEO CHEAP_GRID_CHARGE tuottaa edelleen odotetun battery setpointin ja EV currentin
- HAEO NET_ZERO vaihtaa comboa vartin vaihtuessa
- combo change clear/freeze tapahtuu vain, kun vanha surplus-ohjaus on aktiivinen
- EV `step_a=1` ja `step_a=4` tuottavat tarkoituksellisesti eri current-arvot
- stale HAEO ei aktivoi HAEO NET_ZERO plania
- guard profile estaa HAEO-planin, jos guard ei salli sita

## Suositeltu toteutusjarjestys

1. Lisa device read-model ja mapper-testit.
2. Lisa EV:n W-normalisoinnin sisaiset kentat ilman output-muutosta.
3. Muuta HAEO NET_ZERO plan device-id-pohjaiseksi.
4. Lisa rinnakkainen surplus-device-allokointi traceen.
5. Vaihda policy kayttamaan surplus-device-allokointia.
6. Tuota device-policy vanhojen actuatorien rinnalle.
7. Siirra writer kayttamaan device-policya.
8. Lisa uusi config-loader ja dual-read.
9. Dokumentoi migration ja poista vanhaa toistoa vasta lopuksi.

## Riskit ja hallintakeinot

- Riski: EV:n W/A-muunnos muuttaa kayttaytymista huomaamatta.
  Hallinta: tee conversion parity -testit ennen writer-muutosta.

- Riski: HAEO combo vaihtuu oikealla hetkella, mutta vanha surplus-tila jaa paalle.
  Hallinta: pida combo-change clear/freeze omana testattuna saantona.

- Riski: uusi device-malli abstrahoi liikaa ja peittaa laitekohtaiset erot.
  Hallinta: mallinna erot explicit-kenttina, ei erityistapauksina piilossa.

- Riski: vanha entity-map ja uusi config ajautuvat eri semantiikkaan.
  Hallinta: dual-read-vaiheessa validoi, etta molemmat tuottavat saman device-mallin.

## Avoimet paatokset

- Kaytetaanko EV:n oletusjannitteena aina 230 V per vaihe vai konfiguroitavaa arvoa?
- Onko `power_step_w` aina johdettu adapterissa vai sallitaanko kayttajan antaa se
  suoraan?
- Miten kuvataan device, joka voi seka imea ylijaamaa etta toimia primary loadina?
- Miten vanhat `floor`-nimet mapataan uuteen terminologiaan migration aikana?
- Kuinka kauan legacy trace- ja actuator-kenttia pidetaan rinnalla?

## Ensimmainen konkreettinen PR

Ensimmainen toteutusmuutos kannattaa rajata nain:

- lisa `EmsDeviceConfig` ja `EmsDeviceState`
- lisa mapper nykyisesta entity snapshotista device-malliin
- lisa unit-testit akulle, EV:lle ja releille
- ei muutoksia policy-outputteihin
- ei muutoksia Home Assistant -entityihin

Tama antaa pohjan seuraaville vaiheille ilman, etta kayttajan nakema EMS-ohjaus
muuttuu viela.
