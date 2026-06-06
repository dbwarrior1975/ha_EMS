# EMS Step Model

Tama muistio kuvaa, miten nykyinen EMS-ketju etenee yhdessa skenaariostepissa ja miksi jotkin paatokset nakyvat actuator-tasolla vasta seuraavalla kierroksella.

## Ydinmalli

Yksi `QuarterScenarioHarness.step(...)` ajaa aina samat kolme loopia tassa jarjestyksessa:

1. `ems_policy_engine_loop()`
2. `ems_surplus_latches_loop()`
3. `ems_actuator_writers_loop()`

Tasta seuraa perusmalli:

1. Policy laskee paatokset stepin alun tilasta.
2. Latch-loop toteuttaa dispatch-paatoksen ja paivittaa surplus-active/freezen.
3. Writer-loop kirjoittaa actuatorit policy-outputtien perusteella.

## Tarkein seuraus

`surplus_dispatch_decision` ei ole sama asia kuin actuator-muutos samassa stepissa.

Monissa tilanteissa tapahtuu nain:

1. Policy paattaa nyt, etta joku latch aktivoidaan tai vapautetaan.
2. Latch tekee muutoksen heti samassa stepissa.
3. Writer ei valttamatta viela muuta actuatoria, koska policy command laskettiin ennen latch-muutosta.
4. Seuraavassa stepissa policy nakee uuden latch-tilan ja writer voi vasta silloin toteuttaa nakyvan actuator-muutoksen.

## Missa tama nakyy selvimmin

Tama viive nakyy erityisesti surplus-ohjatuissa kuormissa:

- `surplus_ev_active`
- `surplus_r1_active`
- `surplus_r2_active`
- `surplus_freeze_until_ts`

Policy lukee juuri naita tiloja stepin alussa. Jos latch muuttaa niita saman stepin aikana, uusi vaikutus policy-commandiin nakyy tavallisesti vasta seuraavalla kierroksella.

## EV-esimerkki

Tyypillinen EV-polku:

1. Step A: policy paattaa `RELEASE_EV`
2. Step A: latch asettaa `surplus_ev_active = False`
3. Step A: writer voi silti nahda `policy_ev_current_a = 28`, koska se laskettiin ennen latch-muutosta
4. Step B: policy nakee nyt `surplus_ev_active = False`
5. Step B: policy tuottaa `policy_ev_current_a = 0` ja esimerkiksi `ev_policy_mode = 'restore_min'`
6. Step B: writer laskee EV-currentin minimiin

Siksi on mahdollista, etta samassa stepissa ovat kaikki totta:

- `surplus_dispatch_decision == 'RELEASE_EV'`
- `surplus_ev_active == False`
- writer trace kertoo edelleen `already_matching` ja `new_current_a == 28`

Tama ei ole ristiriita, vaan seurausta loop-jarjestyksesta.

## Releiden logiikka

Sama periaate koskee myos releita, kun niiden command riippuu surplus-latch-tilasta.

Esimerkki aktivoinnista:

1. Policy paattaa `ACTIVATE_RELAY1`
2. Latch asettaa `surplus_r1_active = True`
3. Writer ei valttamatta viela kytke reletta paalle, jos saman stepin `policy_relay1_command` on yha `0`
4. Seuraavassa stepissa policy nakee `surplus_r1_active = True`
5. `policy_relay1_command` muuttuu `1`:ksi
6. Writer kytkee releen paalle

Sama toimii myos release-suunnassa.

## Mita voi tapahtua heti samassa stepissa

Kaikki eivat aina viivasty yhdella stepilla.

Nopea actuator-muutos voi tapahtua jo samassa stepissa, jos policy command perustuu suoraan stepin inputtiin eika juuri saman stepin aikana muuttuneeseen latch-tilaan.

Hyva esimerkki:

- `relay_force_on`

Jos `relay2_force_on=True` stepin alussa, policy voi tuottaa heti `policy_relay2_command = 1`, ja writer voi kytkea relay2:n paalle samassa stepissa.

## Kaytannon saanto testeihin

Kun kirjoitat E2E-skenaariota, erottele aina ainakin nama tasot:

1. `expect_values`
   näkyvat entity-tilat stepin jalkeen
2. `expect_policy`
   policy trace -attribuutit
3. `expect_latch`
   latch trace -attribuutit
4. `expect_writer_trace`
   writer trace -attribuutit

Talla tavalla testi pystyy ilmaisemaan oikein tilanteet, joissa:

- paatos syntyy nyt
- latch muuttuu nyt
- actuator muuttuu vasta seuraavassa stepissa

## Tiivistys

Nykyinen EMS on kaytannossa pipelinoitu tilakone:

1. policy paattaa
2. latch paivittaa tilan
3. writer toteuttaa commandit

Siksi kaikki muutokset eivat nay samassa stepissa, vaikka ne kuuluvat samaan business-tapahtumaan.
