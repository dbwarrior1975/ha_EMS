# Changelog

## Beta 1 — 2026-07-13

Ensimmäinen ulkopuoliseen testaukseen tarkoitettu dokumentoitu beta.

### Käyttäjälle näkyvät ominaisuudet

- strict runtime v5 -pakettipolku
- järjestetty `primary_consuming_device_ids`-fallback
- yksi effective primary per policy-ajo
- EV:n HARD_OFF- tai alle-minimitilanteessa seuraavan primary-kandidaatin kokeilu
- effective primary poistetaan saman tickin surplus-poolista
- sekuntipohjainen RPNZ/RPC yhteisellä 30 sekunnin minimihorisontilla
- järjestetty producer-pooli, hard ceilingit ja toteutumattoman tarpeen diagnostiikka
- unavailable surplus -kandidaatti ei blokkaa seuraavaa eligible-laitetta
- saturoituva `low_pv_cycles`, joka ei julkaise Policy Statea koko yön

### Jakelun dokumentaatiomuutos

- lisätty asennus- ja ensikäynnistysohje
- korvattu osittaiset copy-paste-esimerkit validoiduilla tiedostoreferensseillä
- lisätty oirepohjainen vianetsintä
- erotettu käyttäjä- ja kehittäjädokumentaatio
- poistettu beta-ZIPin juuresta sisäiset implementointi- ja release-verifiointiraportit
- korvattu tuotantokohtaiset entity-ID:t geneerisillä paikkamerkeillä aktiivisissa template-esimerkeissä

### Breaking contract

Runtime policy käyttää listaa:

```text
primary_consuming_device_ids
```

Vanhaa yksittäistä `primary_consuming_device_id`-konfiguraatiokenttää ei hyväksytä strict runtime v5 -paketissa. Diagnostiikan samanniminen summary-kenttä voi edelleen raportoida effective primaryn.

### Tunnetut rajoitteet

Katso [docs/user/known_limitations.md](docs/user/known_limitations.md).
