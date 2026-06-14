# E2E-testien tarinakuvaukset

Tama dokumentti kuvaa nykyiset `tests/e2e_entity`-hakemiston story-kansiot. Vanhat monoliittiset `tests/e2e_entity/test_*.py`-tiedostot on korvattu vaiheistetuilla kansioilla.

Jokaisessa story-kansiossa on oma `scenario_overview.md`, joka on tarkin paikka yksityiskohtaiselle vaihejaolle.

## 1) BATTERY_PROTECT min-cell recovery

Kansio: `tests/e2e_entity/battery_protect_min_cell_recovery/`

Eteneminen:
1. Baseline alkaa `NORMAL_LIMITS`-tilasta turvallisilla SOC- ja min-cell-arvoilla.
2. SOC ja min-cell putoavat raja-arvojen alle, jolloin guard siirtyy `BATTERY_PROTECT`-tilaan.
3. Osittainen palautuminen ei viela riita palautukseen.
4. Kun seka SOC recovery margin etta min-cell threshold tayttyvat, guard palautuu `NORMAL_LIMITS`-tilaan.
5. Min-cell-triggeri ja palautuminen testataan viela uudelleen.

## 2) Goal transition NET_ZERO -> MAX_EXPORT

Kansio: `tests/e2e_entity/goal_transition_net_zero_to_max_export/`

Eteneminen:
1. `NET_ZERO` aktivoi surplus-polun ja EV ehtii burn-tilaan.
2. Goal vaihdetaan `MAX_EXPORT`-tilaan.
3. Surplus-policy kytkeytyy pois, latchit clearataan ja EV siirtyy hard-off-polulle.
4. Testi varmistaa, etta `MAX_EXPORT` pysyy vakaana ilman uusia surplus-aktivointeja.

## 3) NET_ZERO EV hard-off on low PV

Kansio: `tests/e2e_entity/hard_off_on_low_pv/`

Eteneminen:
1. `NET_ZERO` aktivoi RELAY1:n ja ADJUSTABLE/EV-polun.
2. EV nousee burn-virralle.
3. Low-PV-tilanteessa EV vapautetaan ensin restore-min-polkuun.
4. Kun low-PV jatkuu riittavan pitkaan, EV siirtyy hard-offiin.
5. Palautuminen vaatii kelvollisen PV/RPC-tilanteen ja freeze-/hysteresis-ehtojen tayttymisen.

## 4) NET_ZERO EV primary + HOME_BATTERY adjustable

Kansio: `tests/e2e_entity/net_zero_ev_adjustable_load/`

Eteneminen:
1. EV toimii ensisijaisena jatkuvana saato-/kulutuskanavana.
2. HOME_BATTERY toimii `ADJUSTABLE` surplus-targetina.
3. Testit kattavat EV-primary rampin, ADJUSTABLE-aktivoinnin, release-polun, hard-off holdin ja hard-offista palautumisen.

## 5) NET_ZERO force-on relay2 with freeze hygiene

Kansio: `tests/e2e_entity/net_zero_force_on_battery_support/`

Eteneminen:
1. Kayttaja pakottaa RELAY2:n paalle.
2. Force rising-edge luo freeze-jakson, joka estaa liian nopean seuraavan aktivoinnin.
3. RELAY1 aktivointi, vapautus ja RELAY2:n paluu normaaliin surplus-kelpoisuuteen testataan vaiheittain.

## 6) NET_ZERO HOME_BATTERY primary + EV adjustable

Kansio: `tests/e2e_entity/net_zero_homebattery_adjustable_load/`

Eteneminen:
1. HOME_BATTERY toimii ensisijaisena NET_ZERO-saatoelementtina.
2. EV toimii `ADJUSTABLE` surplus-targetina.
3. Testit kattavat activation-gaten, ADJUSTABLE/EV-aktivoinnin, low-PV release- ja hard-off-polun seka reaktivoinnin.

## 7) NET_ZERO priority order

Kansio: `tests/e2e_entity/net_zero_priority_order_quarter/`

Eteneminen:
1. Aktivointijarjestys noudattaa prioriteetteja.
2. Freeze erottaa paatoksen ja seuraavan aktivoinnin.
3. Vapautus tapahtuu matalimman prioriteetin aktiivisesta kohteesta.
4. Lopussa sykli voi kaynnistya uudelleen.

## 8) Optimizer degraded fallback

Kansio: `tests/e2e_entity/optimizer_degraded_fallback/`

Eteneminen:
1. `HORIZON_BY_HAEO` konfiguroi HAEO:n kayttoon.
2. Stale tai puuttuva HAEO-data pudottaa effective forecastin paikalliseen fallbackiin.
3. Runtime jatkaa ilman kaatumista paikallisella policylla.

## 9) System degraded safe mode

Kansio: `tests/e2e_entity/system_degraded_safe_mode/`

Eteneminen:
1. Stale battery inverter heartbeat ajaa guardin `DEGRADED`-tilaan.
2. Akku target clampataan nollaan ja EV/rele-policy menee skip-tilaan.
3. Latchit voidaan clearata, mutta writer ei pakota olemassa olevia EV/rele-actuatoreita pois paalta, jos policy on `-1`.
