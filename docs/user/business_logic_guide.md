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

Surplus-dispatch-statejen idea kayttajalle:

1. Valtetaan sahaava on/off-kayttaytyminen.
2. Hallitaan aktivointi ja vapautus prioriteeteilla.
3. Freeze-ikkuna estaa liian nopeat uudet aktivoinnit.

Tulos:

1. Kuormat kayttaytyvat ennustettavammin.
2. Ohjaus on vakaampaa mittauskohinassa.

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
