# Miten EMS toimii

## Päätösjärjestys

EMS ratkaisee jokaisella policy-ajolla:

1. ovatko runtime-data ja capabilityt valideja
2. mitä guardit sallivat
3. onko käyttäjän FORCE_ON aktiivinen
4. mikä goal on valittu
5. onko HAEO-plan käytettävissä
6. mikä laite saa consuming-, producing- tai surplus-roolin
7. mikä on jokaisen laitteen yksi final `DevicePolicy`

## NET_ZERO

Varttitase muutetaan tavoiteverkkotehoksi. Mitattua grid-tehoa verrataan tähän tavoitteeseen. Sama feedback muodostaa signed control -pyynnön:

```text
positiivinen pyyntö → primary-consuming resolver
negatiivinen pyyntö → producer-pooli
```

Toteutuneen EV:n tai akun komentoa ei lisätä erillisenä feed-forwardina, koska sen vaikutus näkyy jo grid-mittauksessa.

## Primary fallback

```yaml
primary_consuming_device_ids:
  - EV_CHARGER
  - HOME_BATTERY
```

Resolveri käy listan järjestyksessä. EV voidaan ohittaa, jos se ei juuri nyt pysty toteuttamaan pyyntöä. Akku voi tällöin ottaa effective primary -roolin. Jos mikään ei pysty, tarve raportoidaan eikä EMS valitse listan ulkopuolista laitetta.

## Producerit

Producerit käsitellään `producing_priority`-järjestyksessä. Ylemmän prioriteetin kapasiteetti käytetään ensin. Unavailable tai zero-ceiling producer ohitetaan. Toteutumaton osa näkyy diagnostiikassa.

## Surplus

Surplus-laitteet aktivoidaan `priority`-järjestyksessä. Effective primary ei ole samalla tickillä surplus-kandidaatti. Unavailable kandidaatti ohitetaan, mutta strict priority säilyy eligible-laitteiden välillä.

Aktiivisten laitteiden persisted lista säilyttää kytkentäjärjestyksen vanhimmasta uusimpaan. Kun aktiivisia laitteita on enemmän kuin yksi, uusin n−1-lisäkuormaporras voidaan vapauttaa, vaikka RPNZ olisi positiivinen:

```text
excess_consumption_w = max(0, -RPC_w)
release_margin_w = max(100 W, 5 % laitteen tehosta)
release_threshold_w = laitteen teho - release_margin_w
```

Jos excess ylittää release-kynnyksen, uusin laite vapautetaan ja EMS odottaa `surplus_freeze_s`-ajan ennen seuraavan portaan arviointia. Kiinteälle releelle käytetään nimellistehoa. Säädettävälle laitteelle käytetään nykyistä positiivista ohjaustargetia ja sen puuttuessa konfiguroitua surplus-tehoa.

Kun jäljellä on vain ensimmäisenä aktivoitu anchor-laite, sen vapautuksessa käytetään edelleen konservatiivista `RPNZ <= 10 W` -sääntöä.


Min-holdissa olevan EV:n aktivointikynnys on inkrementaalinen. Jos EV kuluttaa jo `min_absorb_w`-tehoa mutta ei ole aktiivisessa SURPLUS-listassa, kynnys lasketaan `max_absorb_w - min_absorb_w`. Aktivoinnin final target pysyy `max_absorb_w`-arvossa. Vastaavasti release takaisin min-holdiin poistaa vain tämän erotuksen verran kulutusta.

## EV HARD_OFF

EV:n low-PV-lifecycle suojaa jatkuvalta turhalta käynnistelyltä. Low-PV counter saturoituu konfiguroituun kynnykseen. HARD_OFF-vapautuksen release-counter etenee, kun PV on peräkkäisillä policy-ajoilla vähintään `low_pv_threshold_w` eikä eksplisiittinen activation block ole aktiivinen. RPC ei kuulu vapautusehtoon. Vapautuminen tekee EV:stä eligible-laitteen; surplus-aktivointi vaatii tämän jälkeen erikseen RPC-kynnyksen ja priority-päätöksen.

## Fail-closed

Puuttuva pakollinen runtime-kenttä, actuator-mapping tai unsupported kind ei aiheuta arvattua fallbackia. EMS raportoi virheen ja estää vaarallisen oletusohjauksen.
