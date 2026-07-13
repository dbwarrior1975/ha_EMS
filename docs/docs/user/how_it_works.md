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

## EV HARD_OFF

EV:n low-PV-lifecycle suojaa jatkuvalta turhalta käynnistelyltä. Low-PV counter saturoituu konfiguroituun kynnykseen. HARD_OFF vapautuu vasta palautumisehdon ja release-counterin jälkeen.

## Fail-closed

Puuttuva pakollinen runtime-kenttä, actuator-mapping tai unsupported kind ei aiheuta arvattua fallbackia. EMS raportoi virheen ja estää vaarallisen oletusohjauksen.
