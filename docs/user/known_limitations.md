# Tunnetut rajoitteet

## Beta-status

Tämä on ensimmäinen ulkopuoliseen testaukseen tarkoitettu beta. Valvomatonta tuotantoajoa ei suositella ennen oman topologian mittaus-, guard- ja writer-testien valmistumista.

## HAEO:n dynaaminen yhdistelmä

HAEO:n NET_ZERO-planin dynaamista primary-vaihtoa ei ole validoitu kaikissa EV–battery-yhdistelmissä. Beta-testissä suositellaan staattista `primary_consuming_device_ids`-järjestystä, ellei HAEO-skenaariota testata erikseen.

## Yksi effective primary

Yhdellä policy-ajolla on enintään yksi effective primary-consuming regulator. Proportional multi-EV split, round-robin tai samanaikainen usean primary-laitteen jako eivät ole toteutettuja.

## Tuetut writer-adapterit

Tuetut kindit ovat `BATTERY`, `EV_CHARGER` ja `RELAY`. Uusi kind vaatii sekä core-capabilityt että writer-adapterin. EMS ei arvaa tuntemattoman laitteen palvelukutsua.

## Kiinteä export-balance stop

RPC-laskennassa on nykyisin kiinteä sääntö:

```text
quarter_energy_balance_kwh >= +0.130 kWh → RPC = 0
```

Kynnys ei ole runtime-konfiguroitava. Tämä voi estää surplus-aktivoinnin tilanteessa, jossa muut laskentakentät näyttävät vielä säätötarvetta. Sääntö on säilytetty toiminnallisen yhteensopivuuden vuoksi, mutta sen domain-perustelu ja tuleva konfiguroitavuus pitää arvioida erikseen.

## Cycle-pohjainen EV lifecycle

HARD_OFF debounce ja PV-pohjainen release käyttävät policy-ajojen määrää, eivät tarkkaa elapsed-aikaa. `low_pv_cycles` saturoituu eikä aiheuta yönaikaista jatkuvaa PS-julkaisua, mutta skipped tickit ja cadence vaikuttavat silti todelliseen kestoon. RPC ei nopeuta eikä hidasta HARD_OFF-vapautusta.

## Template vaatii paikallisen mukautuksen

Paketin active template käyttää geneerisiä entity-ID:itä. Se ei toimi ennen kuin kaikki mittaus-, helper- ja actuator-mappingit on korvattu oman Home Assistant -ympäristön arvoilla.

## Ei command feed-forwardia

NET_ZERO käyttää toteutunutta grid-mittausta feedback-totuutena. Vielä toteutumattomia actuator-komentoja ei lisätä erillisenä feed-forwardina. Nopeissa transienteissa säätö reagoi mittauksen ja rampin tahdissa.

## Surplus activation order

N−1-release käyttää `sensor.ems_active_surplus_devices`-listan järjestystä activation orderina. EMS:n dispatch applier ylläpitää listaa automaattisesti. Manuaalisesti actuatorista päälle tai pois kytketty laite ei muuta listaa, joten manuaalisen ohituksen jälkeen active-state pitää synkronoida tai tyhjentää ennen automaattiohjauksen jatkamista.

