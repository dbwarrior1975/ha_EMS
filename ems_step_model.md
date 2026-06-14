# EMS Step Model

Tama muistio kuvaa, miten nykyinen EMS-ketju etenee yhdessa skenaariostepissa ja miksi jotkin paatokset nakyvat actuator-tasolla vasta seuraavalla kierroksella.

## Ydinmalli

Yksi `QuarterScenarioHarness.step(...)` ajaa aina samat kolme komponenttia tassa jarjestyksessa:

1. `ems_policy_engine_loop()`
2. `ems_dispatch_state_applier_loop()`
3. `ems_actuator_writers_loop()`

Tasta seuraa perusmalli:

1. Policy laskee paatokset stepin alun tilasta.
2. Dispatch state applier toteuttaa dispatch-paatoksen ja paivittaa surplus-active/freezen.
3. Actuator writer loop kirjoittaa actuatorit policy-outputtien perusteella.

## Tarkein seuraus

`surplus_dispatch_decision` ei ole sama asia kuin actuator-muutos samassa stepissa.

Monissa tilanteissa tapahtuu nain:

1. Policy paattaa nyt, etta joku dispatch state aktivoidaan tai vapautetaan.
2. Dispatch state applier tekee muutoksen heti samassa stepissa.
3. Writer ei valttamatta viela muuta actuatoria, koska policy command laskettiin ennen dispatch state-muutosta.
4. Seuraavassa stepissa policy nakee uuden dispatch state-tilan ja writer voi vasta silloin toteuttaa nakyvan actuator-muutoksen.

## Missa tama nakyy selvimmin

Tama viive nakyy erityisesti surplus-ohjatuissa kuormissa:

- `surplus_adjustable_active`
- `surplus_r1_active`
- `surplus_r2_active`
- `surplus_freeze_until_ts`

Policy lukee juuri naita tiloja stepin alussa. Jos dispatch state muuttaa niita saman stepin aikana, uusi vaikutus policy-commandiin nakyy tavallisesti vasta seuraavalla kierroksella.

## EV-esimerkki

Tyypillinen EV-polku:

1. Step A: policy paattaa `RELEASE_ADJUSTABLE`
2. Step A: dispatch state asettaa `surplus_adjustable_active = False`
3. Step A: writer voi silti nahda `policy_ev_current_a = 28`, koska se laskettiin ennen dispatch state-muutosta
4. Step B: policy nakee nyt `surplus_adjustable_active = False`
5. Step B: policy tuottaa `ev_policy_mode = 'restore_min'`; `policy_ev_current_a` on polkukohtainen (EV-primaryssa usein `ev_min_current_a`, muissa release-polussa voi olla `0`)
6. Step B: writer laskee EV-currentin minimiin

Siksi on mahdollista, etta samassa stepissa ovat kaikki totta:

- `surplus_dispatch_decision == 'RELEASE_ADJUSTABLE'`
- `surplus_adjustable_active == False`
- writer trace kertoo edelleen `already_matching` ja `new_current_a == 28`

Tama ei ole ristiriita, vaan seurausta komponenttien ajojarjestyksesta.

## Releiden logiikka

Sama periaate koskee myos releita, kun niiden command riippuu surplus-state-tilasta.

Esimerkki aktivoinnista:

1. Policy paattaa `ACTIVATE_RELAY1`
2. Dispatch state applier asettaa `surplus_r1_active = True`
3. Writer ei valttamatta viela kytke reletta paalle, jos saman stepin `policy_relay1_command` on yha `0`
4. Seuraavassa stepissa policy nakee `surplus_r1_active = True`
5. `policy_relay1_command` muuttuu `1`:ksi
6. Writer kytkee releen paalle

Sama toimii myos release-suunnassa.

## Mita voi tapahtua heti samassa stepissa

Kaikki eivat aina viivasty yhdella stepilla.

Nopea actuator-muutos voi tapahtua jo samassa stepissa, jos policy command perustuu suoraan stepin inputtiin eika juuri saman stepin aikana muuttuneeseen dispatch state-tilaan.

Hyva esimerkki:

- `relay_force_on`

Jos `relay2_force_on=True` stepin alussa, policy voi tuottaa heti `policy_relay2_command = 1`, ja writer voi kytkea relay2:n paalle samassa stepissa.

## Kaytannon saanto testeihin

Kun kirjoitat E2E-skenaariota, erottele aina ainakin nama tasot:

1. `expect_values`
   näkyvat entity-tilat stepin jalkeen
2. `expect_policy`
   policy trace -attribuutit
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
