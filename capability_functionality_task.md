# Capability Functionality Task

Paivitetty: 2026-06-21

Taman dokumentin tarkoitus on seurata tyota, jossa `EMS_config.yaml`-tiedoston
`can_absorb_w` ja `can_produce_w` -capability-booleanit muutetaan oikeasti
logiikkaa ohjaaviksi rajoiksi.

Nykyinen ongelma:

1. YAML antaa ymmartaa, etta device capabilityt ovat tuotantologiikan totuus.
2. Toteutus lukee capabilityt device-read-malliin, mutta core-ohjaus ei viela
   systemaattisesti esta toimintaa niiden perusteella.
3. Esimerkiksi `HOME_BATTERY.can_absorb_w=false` ja `can_produce_w=false` ei
   kayttajan nakokulmasta pitaisi sallia lataus- tai purkuohjausta, mutta nykyinen
   policy voi silti tuottaa akulle wattitargetteja.

Tavoitetila:

`EMS_config.yaml` capabilityt ovat kovia toimintarajoja:

1. `can_absorb_w=false` estaa laitteen kayton kulutuksen/latauksen/absorboinnin
   suuntaan.
2. `can_produce_w=false` estaa laitteen kayton tuotannon/purun/export-avun
   suuntaan.
3. `max_absorb_w` ja `max_produce_w` rajaavat vastaavien suuntien wattitargetit.
4. Capability-esto nakyy traceissa selkeana syyna, ei hiljaisena omituisena
   nollauksena.
5. Writerit eivat kirjoita fyysisesti capabilityn vastaista ohjausta, vaikka
   coreen tulisi virheellinen device policy.

## Valittu semantiikka

| Capability | Target-suunta | Kayttaytyminen |
|---|---|---|
| `can_absorb_w=false` | positiivinen `target_w` | target clampataan nollaan tai laite ohitetaan |
| `can_produce_w=false` | negatiivinen `target_w` | target clampataan nollaan |
| `can_absorb_w=true` | positiivinen `target_w` | sallittu, rajataan `max_absorb_w`:lla |
| `can_produce_w=true` | negatiivinen `target_w` | sallittu, rajataan `max_produce_w`:lla |

Suositeltu fail-safe:

1. policy/core ei valitse capabilityn vastaista laitetta aktiiviseksi
2. jos ristiriita syntyy silti, device policy muutetaan turvalliseksi arvoksi
3. traceen lisataan syy, esimerkiksi `capability_blocked_absorb` tai
   `capability_blocked_produce`
4. writerissa on viimeinen suojakerros, joka ei kirjoita capabilityn vastaista
   targettia

## Vaiheet

| Vaihe | Status | Sisalto |
|---|---|---|
| 1. Baseline ja nykytilan lukitus | completed | nykytila kirjattiin reviewlla ja capability-semantiiikka lukittiin testein |
| 2. Config-validointisaannot | completed | HOME_BATTERY false/false on nyt validaatiovirhe; capability-warningit lisatty |
| 3. Capability helperit coreen | completed | `capabilities.py` keskittaa clamp- ja block-reason -logiikan |
| 4. Policy-engine enforcement | completed | device policyt clampataan capabilityjen mukaan ja surplus-targetit suodatetaan |
| 5. Writer-boundary enforcement | completed | writer neutraloi capabilityn vastaiset akku-, EV- ja relay-ohjaukset |
| 6. Testikattavuus | completed | capability-yksikkotestit, writer- ja engine-regressiot lisatty |
| 7. YAML ja dokumentaatio | completed | tuotanto-YAML paivitetty ja README kuvaa capability-semantiiikan |
| 8. Release-validaatio | completed | testsuite, smoke ja paketointi ajettu onnistuneesti |

## Vaihe 1: Baseline ja nykytilan lukitus

Status: completed

Toteutunut:

1. Nykytila lukittiin reviewlla ja capabilityt vietiin toteutukseen samalla kierroksella.
2. Todistaa, etta `HOME_BATTERY.can_absorb_w=false/can_produce_w=false` ei viela
   estä akkuohjausta.
3. Todistaa, etta device-read-malli lukee booleanit, mutta policy engine ei viela
   kayta niita kovana rajana.

Toteutus:

1. Lisaa regression-testi, joka rakentaa grouped configin capability-arvoilla
   `false/false` ja osoittaa nykyisen ei-toivotun kayttaytymisen.
2. Merkitse testi tarvittaessa xfailiksi, jos se kuvaa tavoitetta ennen toteutusta.
3. Kirjaa havainto tahan dokumenttiin ennen vaihetta 2.

Hyvaksynta:

1. Nykyinen puute on todistettu testilla tai dokumentoidulla failing-testilla.
2. Toteutuksen seuraavat vaiheet voidaan ajaa testivetoisesti.

## Vaihe 2: Config-validointisaannot

Status: completed

Toteutunut:

Config validioi nyt HOME_BATTERY false/false -yhdistelman virheeksi ja varoittaa ristiriitaisista direction/limit -kombinaatioista.

Saannot:

1. Jos `can_absorb_w=false`, mutta `max_absorb_w > 0`, validointi antaa ainakin
   warningin.
2. Jos device on valittu `adjustable_surplus_load`-rooliin, sen pitaa pystyä
   absorboimaan tehoa.
3. Jos device on valittu `adjustable_primary_load`-rooliin NET_ZERO-polulla,
   roolilta vaaditaan siihen liittyva capability:
   - EV primary tarvitsee `can_absorb_w=true`
   - HOME_BATTERY primary tarvitsee vahintaan sen suunnan capabilityt, joita
     kyseinen goal kayttaa
4. Releille pidetaan tiukka saanto:
   - `can_absorb_w=true`
   - `can_produce_w=false`
5. Akulle suositeltu tuotantoarvo on:
   - `can_absorb_w=true`
   - `can_produce_w=true`

Toteutuskohdat:

1. `modules/ems_adapter/config_loader.py`
2. `tests/unit/test_config_loader.py`
3. `tests/contract/test_grouped_config_contract.py`

Hyvaksynta:

1. Virheellinen relay capability kaataa validaation.
2. Harhaanjohtava akku `false/false` antaa warningin tai errorin valitun linjan mukaan.
3. Rooliin valittu absorboimaton device havaitaan ennen runtimea.

Avoin paatos ennen toteutusta:

- Tehdaanko `HOME_BATTERY.can_absorb_w=false/can_produce_w=false` tuotanto-YAML:ssa
  erroriksi vai warningiksi?

Suositus:

- Tee siita error, koska muuten kayttaja voi julkaista configin, joka nayttaa
  poistavan akun kaytosta mutta ei tee sita turvallisesti.

## Vaihe 3: Capability helperit coreen

Status: completed

Toteutunut:

`modules/ems_core/domain/capabilities.py` keskittaa capability clamp- ja block-reason -logiikan.

Toteutus:

1. Lisaa pieni helper-kerros esimerkiksi moduuliin:
   - `modules/ems_core/domain/capabilities.py`
2. Helperit:
   - `can_absorb(device_config)`
   - `can_produce(device_config)`
   - `clamp_target_w_for_capabilities(device_config, target_w)`
   - `capability_block_reason(device_config, target_w)`
3. Kayta olemassa olevaa `EmsDeviceConfig` / `CoreDeviceCapabilitiesConfig` -mallia.

Hyvaksynta:

1. Suuntalogiikka on yhdessä paikassa.
2. Positiivinen target nollautuu, jos `can_absorb_w=false`.
3. Negatiivinen target nollautuu, jos `can_produce_w=false`.
4. Targetit rajataan `max_absorb_w` ja `max_produce_w` -arvoihin.

## Vaihe 4: Policy-engine enforcement

Status: completed

Toteutunut:

Core clampaa device policyt capabilityjen mukaan ja merkitsee estetyt laitteet traceen `capability_blocked_devices`.

Kohdat:

1. `NET_ZERO`
   - akku ei saa latautua, jos `HOME_BATTERY.can_absorb_w=false`
   - akku ei saa purkaa, jos `HOME_BATTERY.can_produce_w=false`
   - EV ei saa aktivoitua, jos `EV_CHARGER.can_absorb_w=false`
   - releet eivat saa aktivoitua, jos `can_absorb_w=false`

2. `MAX_EXPORT`
   - akun purku/export-targetti sallitaan vain jos `can_produce_w=true`
   - jos akku ei voi tuottaa, target on `0 W` ja trace kertoo syyn

3. `CHEAP_GRID_CHARGE`
   - akun lataus sallitaan vain jos `can_absorb_w=true`
   - EV lataus sallitaan vain jos `can_absorb_w=true`

4. Surplus-dispatch
   - `build_surplus_device_targets` suodattaa pois absorboimattomat laitteet
   - force-on ei saa ohittaa fyysista capabilitya

Toteutuskohdat:

1. `modules/ems_core/net_zero/engine.py`
2. `modules/ems_core/net_zero/surplus_device_targets.py`
3. mahdollisesti `modules/ems_adapter/device_read_model.py`, jos core tarvitsee
   device listan helpommin kayttoon

Trace-vaatimukset:

1. `policy_decision_trace` saa kentan kuten `capability_blocked_devices`
2. `device_policies[*].reason` kertoo capability-eston, jos policy nollattiin
3. `dominant_limitation` voidaan myohemmin laajentaa, mutta ensivaiheessa riittaa
   selkea trace-attribuutti

Hyvaksynta:

1. Core-output ei sisalla capabilityn vastaista wattitargettia.
2. Capabilityn estama laite ei aktivoidu surplus-dispatchissa.
3. Trace kertoo miksi laite ei toiminut, vaikka rooli tai goal muuten pyysi sita.

## Vaihe 5: Writer-boundary enforcement

Status: completed

Toteutunut:

Writer neutraloi capabilityjen vastaiset fyysiset kirjoitukset ja vie laitteet turvalliseen tilaan.

Toteutus:

1. Writer lukee runtime device configin tai capability snapshotin.
2. Ennen fyysista kirjoitusta writer tarkistaa:
   - battery positive target vaatii `can_absorb_w=true`
   - battery negative target vaatii `can_produce_w=true`
   - EV target > 0 vaatii `can_absorb_w=true`
   - relay ON vaatii `can_absorb_w=true`
3. Jos kirjoitus estetaan, writer traceen:
   - `reason = capability_blocked_absorb` tai `capability_blocked_produce`
   - `written = false`

Toteutuskohdat:

1. `ems_actuator_writers.py`
2. `modules/ems_adapter/runtime_context.py`
3. `tests/unit/test_writer_semantics.py`

Hyvaksynta:

1. Virheellinen device policy ei johda fyysiseen kirjoitukseen.
2. Writer trace nayttaa eston syyn.

## Vaihe 6: Testikattavuus

Status: pending

Pakolliset testit:

1. Config validation
   - akku `false/false` + aktiiviset rajat havaitaan
   - absorboimaton adjustable device havaitaan
   - releiden capabilityt validoidaan

2. Device read model
   - YAML capabilityt luetaan oikein
   - tuotanto-YAML:n akku on `can_absorb_w=true`, `can_produce_w=true`

3. Core engine
   - `NET_ZERO`: akku ei lataa kun `can_absorb_w=false`
   - `NET_ZERO`: akku ei pura kun `can_produce_w=false`
   - `MAX_EXPORT`: akku ei pura kun `can_produce_w=false`
   - `CHEAP_GRID_CHARGE`: EV ei lataudu kun `can_absorb_w=false`

4. Surplus targetit
   - absorboimaton EV ei ole `ADJUSTABLE`-kandidaatti
   - absorboimaton relay ei aktivoidu

5. Writer
   - writer estaa capabilityn vastaiset battery-, EV- ja relay-kirjoitukset

6. E2E
   - yksi rajattu scenario, jossa EV tai akku on capabilitylla disabloitu ja EMS
     pysyy turvallisesti nollassa

Hyvaksynta:

1. `PYTHONPATH=modules python3 -m pytest -q tests/unit/test_config_loader.py tests/unit/test_device_read_model.py tests/unit/test_engine.py tests/unit/test_writer_semantics.py`
2. `PYTHONPATH=modules python3 -m pytest -q tests/e2e_entity`

## Vaihe 7: YAML ja dokumentaatio

Status: pending

Toteutus:

1. Paivita `EMS_config.yaml` tuotantoarvot:
   - `HOME_BATTERY.can_absorb_w: true`
   - `HOME_BATTERY.can_produce_w: true`
2. Paivita `example_EMS_config.yaml` samalla semantiikalla.
3. Dokumentoi README:ssa capabilityjen merkitys:
   - booleanit ovat toiminnallisia rajoja
   - `false` tarkoittaa, etta EMS ei kayta kyseista suuntaa
4. Paivita operointi-ohje:
   - miten tunnistaa capabilityn estama ohjaus traceista

Hyvaksynta:

1. Uusi kayttaja ei voi lukea YAML:sta vaaraa oletusta akun disabloinnista.
2. Capability-estot ovat nakyvissa operointidokumentaatiossa.

## Vaihe 8: Release-validaatio

Status: pending

Aja:

1. `PYTHONPATH=modules python3 -m pytest -q tests`
2. `PYTHONPATH=modules python3 -m pytest -q tests/smoke/test_pyscript_ast_compat.py`
3. `./zippaa_ems.sh -o /tmp/ems_capability_functionality_release.zip`

Hyvaksynta:

1. Testsuite on vihrea, pois lukien tarkoituksellinen xfail.
2. Pyscript AST -smoke menee lapi.
3. Release-paketti syntyy ja sisaltaa `EMS_config.yaml`.

## Riskit

1. Capabilityt voivat muuttaa tuotantokayttaytymista heti, jos nykyinen YAML on
   ristiriidassa todellisen toivotun kayton kanssa.
2. Akku `false/false` on erityisen riskialtis: jos booleanit otetaan kayttoon
   ennen YAML-korjausta, EMS voi lopettaa akun ohjauksen kokonaan.
3. Writer-boundary enforcement tarvitsee runtime capabilityt kirjoittajan
   kayttoon ilman etta se tekee writerista liian riippuvaista core-rakenteesta.
4. E2E-odotusarvot muuttuvat niissa tapauksissa, joissa vanha logiikka salli
   capabilityn vastaisen targetin.

## Lopullinen Definition of Done

1. `can_absorb_w` ja `can_produce_w` vaikuttavat oikeasti policyyn ja writeriin.
2. Capabilityn vastainen ohjaus ei paady actuatorille.
3. Trace kertoo capability-eston syyn.
4. Tuotanto-YAML kuvaa akun, EV:n ja releiden todelliset kyvykkyydet.
5. Uusi kayttaja voi paatella YAML:sta oikein, mita EMS saa ohjata.
6. Koko testsuite ja release-paketointi menevat lapi.
