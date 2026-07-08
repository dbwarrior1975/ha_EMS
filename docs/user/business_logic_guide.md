# EMS Business Logic Guide

Tama dokumentti kuvaa EMS:n energiastrategian kayttajan nakokulmasta: mita jarjestelma yrittaa optimoida ja milla prioriteetilla.

## Tavoite yhdella lauseella

EMS tasapainottaa akun, EV-laturin ja relekuormat niin, etta valittu tavoitetila toteutuu turvallisuusrajojen sisalla.

## Optimointihierarkia

Korkeimman prioriteetin asiat ensin:

1. Turvallisuus
2. Kayttajan eksplisiittiset valinnat
3. Valittu energiatavoite
4. Ennusteohjaus (jos data on tuoretta)
5. Mukavuus ja hienosaato

## 1) Turvallisuus ennen kaikkea

Guard-tilat voivat rajata tai estaa optimointia:

1. `DEGRADED`: data on stale/invalid -> optimointi supistetaan turvalliseen minimiin.
2. `BATTERY_PROTECT`: akun suojelu menee kaiken muun edelle.
3. `STRICT_LIMITS`: kayttajan pakottamat tehorajat rajaavat toimintaa.
4. `NORMAL_LIMITS`: normaali optimointi sallittu.

Kaytannon merkitys:

1. Vaikka goal olisi `NET_ZERO`, guard voi pakottaa konservatiivisempaan toimintaan.
2. Safety override voittaa aina pelkan optimointihyodyn.

## 2) Kayttajan valinnat ovat seuraava taso

EMS kunnioittaa kayttajan tekemia valintoja:

1. `control_profile` paattaa kuka johtaa: kayttaja vai automatiikka.
2. `goal_profile` paattaa mihin suuntaan optimointi tehdaan.
3. force-asetukset (esim. EV current, relay force) toimivat tarkoituksellisina overrideina valituissa profiileissa.

## 3) Goal-profiilien tarkoitus kayttajalle

### `NET_ZERO`

Paatavoite:

1. Tasata verkko-ostoa paikallisesti neljannesjaksoissa.
2. Kayttaa surplus-kohteita prioriteettien mukaan.

Kayttajan odotus:

1. Akku toimii paasaantoisesti aktiivisena tasaajana.
2. EV/releet aktivoituvat kun surplus-ehdot tayttyvat.

### `MAX_EXPORT`

Paatavoite:

1. Maksimoida vientisuuntaa.

Kayttajan odotus:

1. EV-joustolataus pois.
2. Releet pois.
3. Akun tavoite painottuu vientiin.

### `CHEAP_GRID_CHARGE`

Paatavoite:

1. Ladata halvalla (tai ennusteen perusteella edullisesti).

Kayttajan odotus:

1. EV-lataus ja akun lataus ovat aktiivisempia.
2. Releet pysyvat pois paalta.

## 4) Miten surplus-logiikka palvelee strategiaa

NET_ZERO kasittelee surplusia device-/policy-vetoisena kandidaattipoolina.
Osallistuva laite tarvitsee `can_absorb_w=true` ja `surplus_allowed=true`. Sen
jarjestys tulee omasta `priority`-arvosta. Aktivointikynnys on aina laitteen
`capabilities.max_absorb_w`, ja aktiivinen target tulee omasta
`surplus_dispatch_mode`-strategiasta (`max_absorb` tai `fixed`).

Useampi EV voi olla samassa poolissa. Korkeampi priority arvioidaan ensin, ja
nykyinen strict-priority-semantikka sailyy: alempi laite ei ohita blokattua
ylempaa first-feasible-periaatteella. Aktiiviset EV:t saavat omat
`DevicePolicy`-targetit; release ei vaadi, etta vain yksi EV olisi "valittu".


Surplus-dispatch-statejen idea kayttajalle:

1. Valtetaan sahaava on/off-kayttaytyminen.
2. Hallitaan aktivointi ja vapautus prioriteeteilla.
3. Freeze-ikkuna estaa liian nopeat uudet aktivoinnit.

Tulos:

1. Kuormat kayttaytyvat ennustettavammin.
2. Ohjaus on vakaampaa mittauskohinassa.

### FORCE_ON ja control-feedbackin esto

`force_on=true` tarkoittaa eksplisiittista kayttajan tahdonilmaisua: laite
halutaan paalle, vaikka NET_ZERO-tavoite ei sen seurauksena toteutuisi. EV:n
FORCE_ON etenee capabilityn rajaamaan positiiviseen `DevicePolicy.target_w`-
arvoon ja fyysiseen enable/current-kirjoitukseen.

FORCE_ON ohittaa optimointiperusteiset estot, kuten surplus-kynnyksen,
`surplus_allowed`-eligibilityn, low-PV/HARD_OFF-lifecycle-eston, HAEO:n
NET_ZERO-plan-limitin ja primary/residual feedback-optimointiblokin. HARD_OFF-
lifecycle-statea ei kuitenkaan nollata: se voi pysya taustalla aktiivisena ja
palata voimaan heti, kun FORCE_ON poistuu.

FORCE_ON ei ohita aitoa turvallisuus- tai toteutusestetta. Esimerkiksi
`guard=DEGRADED`, puuttuva absorb-capability, invalidi laite/writer-polku tai muu
fyysinen safety-interlock voi edelleen estaa aktuaattorikomennon.

Feedback-suojaus ei perustu enaa siihen, etta PV on matala ja akun setpoint
negatiivinen. Se aktivoituu vain, jos absorboiva primary ja eri tuottava residual-
regulaattori muodostavat todellisen control-loop-riskin. Paatos perustuu rooleihin,
capabilityihin ja residual-regulaattorin todelliseen tuotantotilaan. FORCE_ON-
tilassa EV-target on kiintea capability-rajoitettu kayttajapyynto, ei vapaasti
kasvava primary-regulation-muuttuja.

Quarter-release kaytanto:

1. EMS ei vapauta aktiivista surplus-kuormaa vain siksi, etta vartti vaihtui.
2. Vapautus perustuu edelleen policy-ehtoihin, erityisesti `rpnz_w`:aan.
3. Pieni positiivinen `rpnz_w`, valilla `+1 ... +10 W`, kasitellaan kaytannollisena nollana aktiivisen release-paattelyn kannalta.
4. Jos aktiivinen EV tai rele on paalla ja `rpnz_w <= 10 W`, EMS vapauttaa alimman prioriteetin aktiivisen surplus-kohteen.
5. Tama auttaa tilanteessa, jossa vartin alussa pieni negatiivinen kvartaalitase tuottaa esimerkiksi vain `+4 W` RPNZ:n.

## 5) Ennusteiden rooli kayttajan nakokulmasta

Ennusteet auttavat vain, jos ne ovat tuoreita ja sallittuja profiileissa.

1. Jos HAEO-data on tuoretta, sita voidaan kayttaa battery/EV-targetteihin tietyissa goal-tiloissa.
2. Jos data ei ole tuoretta, EMS palaa paikalliseen fallback-logiikkaan.

## 6) Mita kayttaja nakee kaytannossa

Kun EMS toimii oikein, kayttaja havaitsee:

1. guard-tila kertoo turvallisuuskehyksen
2. goal kertoo optimointisuunnan
3. policy trace kertoo miksi paatos tehtiin
4. actuator writer trace kertoo toteutuiko paatos fyysisena ohjauksena

## 7) Tunnettu strateginen rajaus

Nykysemantiikassa `DEGRADED` ei automaattisesti pakota kaikkia jo paalla olevia EV/rele-actuatoreita pois paalta.

Tama on tietoinen toimintatapa, joka kannattaa kasitella erillisena riski- ja operointipaatoksena ennen 1.0-julkaisua.

## Liittyvat dokumentit

1. `docs/dev/tilakaavio.md`
2. `docs/dev/arkkitehtuuri.md`
3. `docs/user/operointi.md`
4. `docs/dev/ems_step_model.md`
