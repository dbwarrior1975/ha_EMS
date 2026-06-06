# HAEO Esitutkimus

## Tavoite

Tama dokumentti tiivistaa nykyisen HAEO forecast -semantiikan, nykykoodissa nakyvat jaljet alkuperaisesta `NET_ZERO`-ajatuksesta seka luonnoksen jatkomallista, jossa HAEO forecast ohjaa akun ja EV:n keskinaista allokaatiosuhdetta.

## Nykyinen HAEO-semantiikka

Nykykoodissa HAEO tuo sisaan kaksi forecast-lahdetta:

1. akun target `battery_target_kw`
2. EV target `ev_target_kw`

Syotteet luetaan entiteeteista:

1. `sensor.haeo_battery_power_active`
2. `sensor.haeo_ev_battery_power_active`
3. `sensor.battery_active_power`
4. `sensor.ev_akut_active_power`
5. `input_number.ems_haeo_stale_timeout_s`

Forecast payload odottaa entryja, joissa on:

1. `time`
2. `value`

Kayttoon valitaan uusin piste, jonka `time <= now`.

## Freshness-logiikka

HAEO on effective vain jos:

1. forecast on konfiguroitu kayttoon
2. akun freshness-lahde on tuore
3. EV freshness-lahde on tuore

Nykyinen freshness on all-or-nothing:

1. jos battery freshness stale -> HAEO stale
2. jos EV freshness stale -> HAEO stale
3. vasta kun molemmat ovat tuoreita -> `effective_forecast = HAEO`

## Missa HAEO vaikuttaa nyt

### Akku

HAEO vaikuttaa akun targettiin vain goal-profiileissa:

1. `MAX_EXPORT`
2. `CHEAP_GRID_CHARGE`

Muulloin akku kayttaa paikallista logiikkaa.

### EV

HAEO vaikuttaa EV:hen vain goal-profiilissa:

1. `CHEAP_GRID_CHARGE`

Muissa goal-tiloissa EV ei kayta HAEO EV-targettia.

### `NET_ZERO`

Nykykoodissa HAEO ei ohjaa `NET_ZERO`-tilassa akun ja EV:n keskinaista suhdetta.

`NET_ZERO`-tilassa:

1. akku kayttaa paikallista `candidate_sp_net_zero()`-logiikkaa
2. EV kayttaa paikallista burn/force-logiikkaa
3. surplus-policy perustuu paikalliseen RPC/RPNZ-logiikkaan

HAEO näkyy `NET_ZERO`-tilassa lahinna trace- ja forecast-awareness-tasolla.

## Jaljet alkuperaisesta `NET_ZERO`-ajatuksesta

Koodissa on selvia merkkeja siita, että HAEO:n piti liittya `NET_ZERO`-tilaan nykyista enemman:

1. `HORIZON_BY_HAEO` control-profiili
2. `NET_ZERO`-selitetekstit forecast-aware muodossa
3. `FORECAST_FALLBACK_LOCAL` limitation
4. se, etta effective HAEO estaa nykyisin surplus-policyn aktivoitumisen `NET_ZERO`-tilassa

Nykyinen seliteteksti sanoo suoraan:

1. `Net zero goal with HAEO forecast visible, but local policy remains dominant`

Tama viittaa siihen, etta forecast-aware `NET_ZERO`-suunta on ollut olemassa ajatuksena, mutta akun ja EV:n varsinainen forecast-pohjainen jako ei ole toteutettu.

## Alkuperaisen ajatuksen tulkinta

Tarkoitus ei ollut, että HAEO antaisi `NET_ZERO`-tilassa absoluuttiset toteutuskaskyt:

1. akku = tasan `2000 W`
2. EV = tasan `4000 W`

Vaan että HAEO antaisi akun ja EV:n keskinaisen suhteen.

Esimerkki:

1. battery `2 kW`
2. EV `4 kW`

Nykykayttajalle vastaava kasin tehtava allokaatio olisi suunnilleen:

1. `max_solar_charge_w = 2000`
2. `ev_max_current_a ~= 16 A`

Jos todellinen kaytettavissa oleva joustava latausteho onkin pienempi kuin forecast olettaa, semanttisesti luontevampaa olisi, että akku ja EV jakavat kaytettavissa olevan tehon samassa suhteessa eivatka niin, että akku pitaisi absoluuttisen targetin ja EV saisi vain rippeet.

## Ehdotettu vaihtoehto 2: HAEO ratio `NET_ZERO`:ssa

Ehdotettu semantiikka:

1. HAEO forecast ei maarita `NET_ZERO`-tilassa absoluuttisia targetteja
2. HAEO forecast maarittaa akun ja EV:n keskinaisen allokaatiosuhteen
3. paikallinen EMS jakaa kaytettavissa olevan joustavan latausbudjetin taman suhteen mukaan
4. paikalliset rajat pysyvat aina ylimpina

### Share-basis

Suositeltu tulkinta:

1. `battery_share_basis_kw = max(battery_target_kw, 0)`
2. `ev_share_basis_kw = max(ev_target_kw, 0)`

Perustelu:

1. negatiivinen battery-target ei sovi suoraan latausallokaatioon
2. negatiivinen EV-target ei sovi latausallokaatioon
3. ratio toimii latauspriorisoinnin antajana, ei purkustrategiana

### Suhteen muodostus

Jos molemmat share-basis-arvot ovat positiivisia:

1. `battery_ratio = battery_share_basis / (battery_share_basis + ev_share_basis)`
2. `ev_ratio = ev_share_basis / (battery_share_basis + ev_share_basis)`

Esimerkki:

1. battery `2 kW`
2. EV `4 kW`

-> ratio:

1. battery noin `33 %`
2. EV noin `67 %`

Jos kaytettavissa oleva joustava latausbudjetti on vain `3 kW`, alustava jako olisi:

1. battery noin `1 kW`
2. EV noin `2 kW`

### Fallbackit

Fallback nykyiseen paikalliseen `NET_ZERO`-logiikkaan, jos:

1. `effective_forecast != HAEO`
2. share-basis-arvoja ei synny
3. molemmat share-basis-arvot ovat `0`
4. guard tai muu paikallinen rajoite estaa forecast-avusteisen allokaation

## Tarkeimmat avoimet maaritykset jatkoa varten

1. Mikä on tarkka “jaettava budjetti” `NET_ZERO`-tilassa?
2. Pysyyko `ev_force_current_a` EV:n floorina myos ratio-mallissa?
3. Saako surplus-policy olla aktiivinen samaan aikaan effective HAEO:n kanssa?
4. Vaikuttaako ratio vain lataukseen vai myos akun purkupuoleen?
5. Pitaako freshness jatkossakin olla all-or-nothing vai battery/EV-kohtainen?

## Suositus jatkoon

Luontevin jatkosuunta on, että HAEO toimii `NET_ZERO`-tilassa akun ja EV:n suhteellisen allokaation antajana, ei absoluuttisena toteutusmoottorina.

Tama sopii hyvin nykyarkkitehtuuriin, koska:

1. paikallinen EMS voi edelleen hoitaa reaaliaikaisen net-zero-balance-korjauksen
2. HAEO voi tuoda 3 vrk horisontin priorisoinnin ilman että koko `NET_ZERO`-moottori korvataan
3. paikalliset rajat kuten `max_solar_charge_w` ja `ev_max_current_a` voivat pysya ylimpina rajoina
