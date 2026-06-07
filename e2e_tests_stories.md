# E2E-testien tarinakuvaukset

Tama dokumentti kuvaa suomeksi, miten kukin `tests/e2e_entity`-hakemiston testikeissi etenee vaihe vaiheelta.

## 1) test_battery_protect_min_cell_trigger_and_recovery_quarter
Tiedosto: `tests/e2e_entity/test_battery_protect_min_cell_recovery_quarter2.py`

Eteneminen:
1. Alkuun jarjestelma on normaalissa guard-tilassa (`NORMAL_LIMITS`) turvallisilla SOC- ja kennon jannitearvoilla.
2. SOC ja minimi kennonjannite putoavat raja-arvojen alle, jolloin guard siirtyy `BATTERY_PROTECT`-tilaan.
3. Osittainen palautuminen ei viela riita: guard pysyy `BATTERY_PROTECT`-tilassa.
4. Kun palautumisehdot tayttyvat kokonaan, guard palautuu takaisin `NORMAL_LIMITS`-tilaan.
5. Minimi kennonjannite putoaa uudelleen, jolloin `BATTERY_PROTECT` aktivoituu uudestaan.
6. Kun palautumisehdot taas tayttyvat, guard palautuu toistamiseen normaaliin.

## 2) test_goal_transition_net_zero_ev_burn_to_max_export_hard_off_and_clear_latches
Tiedosto: `tests/e2e_entity/test_goal_transition_net_zero_to_max_export.py`

Eteneminen:
1. Testi kaynnistyy `NET_ZERO`-tilasta, jossa ensin aktivoidaan RELAY1 ja sen jalkeen EV.
2. EV ehtii burn-tilaan (korkea virta) ja rele-/surplus-stateit ovat aktiivisia.
3. Tavoite vaihdetaan `MAX_EXPORT`-tilaan.
4. Surplus-politiikka kytkeytyy pois paalta, latchit nollataan (`CLEAR_ALL`) ja EV siirtyy hard-off-polulle.
5. Kirjoittaja varmistaa, etta EV disabletaan, virta palautetaan minimiin laturin ollessa pois, ja releet vapautetaan.
6. Lopussa tarkistetaan, etta `MAX_EXPORT`-tila pysyy vakaana ilman uusia aktivaatioita.

## 3) test_net_zero_priority_order_one_quarter
Tiedosto: `tests/e2e_entity/test_net_zero_priority_order_quarter.py`

Eteneminen:
1. `NET_ZERO`-tilassa aktivointijarjestys etenee prioriteetin mukaan: RELAY1 -> EV -> RELAY2.
2. Freeze-ikkunat erottavat paatoksen syntymisen ja fyysisen toteuman nakymisen.
3. Kun surplus romahtaa, vapautus tapahtuu kaanteisessa jarjestyksessa: RELAY2 -> EV -> RELAY1.
4. Testi varmistaa jokaisessa vaiheessa dispatch state-, policy- ja actuator-nakyvyyden eron.
5. Lopussa sykli kaynnistyy uudelleen ja RELAY1 voidaan aktivoida taas ensimmaisena.

## 4) test_net_zero_user_forces_relay2_with_freeze_hygiene
Tiedosto: `tests/e2e_entity/test_net_zero_force_on_battery_support.py`

Eteneminen:
1. Alussa ei ole aktiivia surplus-kuormia, ja RPC on alle RELAY2-kynnyksen.
2. Kayttaja pakottaa RELAY2:n paalle (`relay2_force_on=True`), jolloin syntyy force-pohjainen freeze-jakso.
3. Freeze-jakson aikana RELAY1 ei saa aktivoitua, vaikka muuten voisi.
4. Freeze-jakson jalkeen RELAY1-aktivointi sallitaan normaalin logiikan kautta.
5. Kun RPNZ laskee, RELAY1 vapautetaan mutta pakotettu RELAY2 pysyy paalla.
6. Kun kayttaja poistaa pakotuksen, RELAY2 palaa normaaliin surplus-kelpoisuuteen.
7. Taman jalkeen RELAY2 voidaan aktivoida normaalisti, siita syntyy uusi freeze, ja lopuksi RELAY1 aktivoidaan taas hallitusti.

## 5) test_net_zero_ev_stays_at_min_first_then_hard_off_when_low_pv_persists_spec
Tiedosto: `tests/e2e_entity/test_net_zero_ev_hard_off_on_low_pv_spec.py`

Eteneminen:
1. `NET_ZERO`-surplus aktivoi ensin RELAY1:n ja sitten EV:n, joka nousee burn-virralle.
2. Kun PV putoaa alle rajan ja surplus loppuu, EV vapautetaan ensin normaalisti (release), ei heti hard-offiin.
3. Seuraavalla matalan PV:n syklilla EV palautetaan ensin minimivirralle (restore-min-polku).
4. Kun matala PV jatkuu riittavan pitkasti, EV siirtyy hard-off-tilaan ja laturi poistetaan kaytosta.
5. Vaikka PV palautuu, hard-off pysyy aktiivisena kunnes surplus-polku aktivoi EV:n uudelleen kelvollisessa tilanteessa.
6. Lopussa tarkistetaan, etta EV palaa normaaliin aktivointiin kun RPC/PV taas riittavat.

## 6) test_optimizer_stale_reactive_fallback
Tiedosto: `tests/e2e_entity/test_optimizer_degraded_fallback.py`

Eteneminen:
1. Ohjaus on `HORIZON_BY_HAEO`, mutta HAEO-lahteet merkitsevat stale-tilaa.
2. Yhdella stepilla tarkistetaan, etta konfiguroitu ennuste on HAEO, mutta tehokas ennuste putoaa paikalliseen (`NONE`) fallbackiin.
3. Dominant limitation -kentasta varmistetaan fallback-syy (`FORECAST_FALLBACK_LOCAL`).

## 7) test_forecast_missing_keeps_runtime_alive
Tiedosto: `tests/e2e_entity/test_optimizer_degraded_fallback.py`

Eteneminen:
1. Ohjaus on `HORIZON_BY_HAEO`, mutta ennustedata puuttuu (`forecast=None`) ja lahteet ovat stale.
2. Testi varmistaa, etta runtime ei kaadu vaan jatkaa paikallisella fallback-politiikalla.
3. Lopputuloksena akun tavoite ja EV-virta vastaavat local cheap-grid-charge -kayttaytymista.

## 8) test_soc_stale_enters_safe_mode
Tiedosto: `tests/e2e_entity/test_system_degraded_safe_mode.py`

Eteneminen:
1. battery inverter heartbeat asetetaan stale-tilaan.
2. Yhdella stepilla guard siirtyy `DEGRADED`-tilaan.
3. Samalla politiikka clampataan turvalliseen moodiin: akun tavoite 0 W ja EV-policy -1 (safe/degraded-kayttaytyminen).
4. Paatosjalki vahvistaa rajoitteen syyksi `SYSTEM_DEGRADED`.

## 9) test_writer_freeze_in_system_degraded
Tiedosto: `tests/e2e_entity/test_system_degraded_safe_mode.py`

Eteneminen:
1. Aluksi simuloidaan, etta EV ja relay1 ovat aktiivisia.
2. battery inverter heartbeat stale-tilan seurauksena jarjestelma menee `DEGRADED`-tilaan.
3. Latch-tilat nollataan, mutta kirjoittaja ei pakota aktuattoreita uuteen tilaan, vaan skipataan policy-syysta.
4. Testi varmistaa writer-tracesta, etta EV:n ja relay1:n syy on `policy_skip`.
