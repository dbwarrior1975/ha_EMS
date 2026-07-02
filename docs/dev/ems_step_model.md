# EMS Step Model

Tama muistio kuvaa, miten nykyinen EMS-ketju etenee yhdessa skenaariostepissa ja miksi jotkin paatokset nakyvat actuator-tasolla vasta seuraavalla kierroksella.

## Ydinmalli

Yksi `QuarterScenarioHarness.step(...)` ajaa aina samat kolme komponenttia tassa jarjestyksessa:

1. `ems_policy_engine_loop(trigger_reason='e2e')`
2. `ems_dispatch_state_applier_loop()`
3. `ems_actuator_writers_loop()`

Tasta seuraa perusmalli:

1. Policy laskee paatokset stepin alun tilasta.
2. Dispatch state applier toteuttaa dispatch-paatoksen ja paivittaa surplus-active/freezen.
3. Actuator writer loop kirjoittaa actuatorit policy-outputtien perusteella.

E2E ei odota oikeaa seinakellotimeria. Harness kutsuu policy-loopin wrapperia
suoraan, jotta yksi step simuloi yhden deterministisen sampling-ajon.
Tama ohittaa tuotannon `2s` scheduler-skip-polun ja pakottaa
`policy_diagnostics`-julkaisun `trigger_reason='e2e'`-arvolla.

## Tarkein seuraus

`surplus_device_dispatch_decision` ei ole sama asia kuin actuator-muutos samassa stepissa.

Monissa tilanteissa tapahtuu nain:

1. Policy paattaa nyt, etta joku dispatch state aktivoidaan tai vapautetaan.
2. Dispatch state applier tekee muutoksen heti samassa stepissa.
3. Writer ei valttamatta viela muuta actuatoria, koska policy command laskettiin ennen dispatch state-muutosta.
4. Seuraavassa stepissa policy nakee uuden dispatch state-tilan ja writer voi vasta silloin toteuttaa nakyvan actuator-muutoksen.

## Missa tama nakyy selvimmin

Tama viive nakyy erityisesti surplus-ohjatuissa kuormissa ja niihin liittyvassa
kanonisessa tilassa:

- `active_surplus_devices`
- `surplus_freeze_until_ts`

Policy lukee juuri naita tiloja stepin alussa. Jos dispatch state muuttaa niita
saman stepin aikana, uusi vaikutus `device_policies`-ulostuloon nakyy
tavallisesti vasta seuraavalla kierroksella.

Huomio konfiguraatiosopimuksesta: `runtime.*`-entityt ovat kayttajan
konfiguroitavia input-pintoja, mutta `device_policies`, `dispatch_command`,
`policy_state` ja diagnostiikkasensorit ovat kiinteita canonical output
surfaceja koodissa.

## EV-esimerkki

Tyypillinen EV-polku:

1. Step A: policy paattaa `RELEASE_ADJUSTABLE`
2. Step A: dispatch state poistaa `EV_CHARGER`:n kanonisesta `active_surplus_devices`-tilasta
3. Step A: writer voi silti nahda saman stepin aikana vanhan `EV_CHARGER`-device-policyn, koska se laskettiin ennen dispatch state -muutosta
4. Step B: policy nakee nyt paivitetyn `active_surplus_devices`-tilan
5. Step B: policy tuottaa uuden `EV_CHARGER`-device-policyn, jossa moodi on tyypillisesti `restore_min` tai `hard_off`
6. Step B: writer toteuttaa uuden pyynnon actuator-tasolle

Siksi on mahdollista, etta samassa stepissa ovat kaikki totta:

- `surplus_device_dispatch_decision == 'RELEASE_ADJUSTABLE'`
- `active_surplus_devices` ei enaa sisalla `EV_CHARGER`:a
- writer trace kertoo edelleen `already_matching` tai toteuttaa viela vanhaa targetia

Tama ei ole ristiriita, vaan seurausta komponenttien ajojarjestyksesta.

## Releiden logiikka

Sama periaate koskee myos releita, kun niiden command riippuu surplus-state-tilasta.

Esimerkki aktivoinnista:

1. Policy paattaa `ACTIVATE_RELAY1`
2. Dispatch state applier lisaa `RELAY1`:n `active_surplus_devices`-tilaan
3. Writer ei valttamatta viela kytke reletta paalle, jos saman stepin `RELAY1`-device-policy on yha `enabled=false`
4. Seuraavassa stepissa policy nakee `RELAY1`:n aktiivisena
5. `RELAY1`-device-policy muuttuu `enabled=true`
6. Writer kytkee releen paalle

Sama toimii myos release-suunnassa.

## Mita voi tapahtua heti samassa stepissa

Kaikki eivat aina viivasty yhdella stepilla.

Nopea actuator-muutos voi tapahtua jo samassa stepissa, jos policy command perustuu suoraan stepin inputtiin eika juuri saman stepin aikana muuttuneeseen dispatch state-tilaan.

Hyva esimerkki on relelaite, jonka oma `policy.force_on` -entity on `True`
stepin alussa. Tassa tilanteessa policy voi tuottaa heti kyseiselle
device-id:lle paalle-kaskyn `device_policies`-payloadissa, ja writer voi
kytkea releen paalle samassa stepissa.

## Kaytannon saanto testeihin

Kun kirjoitat E2E-skenaariota, erottele aina ainakin nama tasot:

1. `expect_values`
   näkyvat entity-tilat stepin jalkeen
2. `expect_policy`
   policy trace -attribuutit
3. `expect_device_policies`
   kanoniset device-kohtaiset ohjauspyynnot
3. `expect_dispatch_state`
   dispatch state trace -attribuutit
4. `expect_writer_trace`
   writer trace -attribuutit

Talla tavalla testi pystyy ilmaisemaan oikein tilanteet, joissa:

- paatos syntyy nyt
- dispatch state muuttuu nyt
- actuator muuttuu vasta seuraavassa stepissa

## Tiivistys

Nykyinen EMS on kaytannossa pipelinoitu tilakone:

1. policy paattaa
2. dispatch state paivittaa tilan
3. writer toteuttaa commandit

Siksi kaikki muutokset eivat nay samassa stepissa, vaikka ne kuuluvat samaan business-tapahtumaan.
