# Changelog

## Beta 1.2 — 2026-07-13

### Incremental n−1 surplus release

- Usean aktiivisen surplus-laitteen release käyttää persisted activation orderia: ensimmäinen laite on anchor ja viimeinen uusin n−1-portaista.
- Uusin porras vapautetaan, kun `max(0, -RPC_w)` ylittää laitteen `releasable_power_w`-arvon marginaalilla `max(100 W, 5 % tehosta)`.
- Fixed relay käyttää nimellistehoa; säädettävä laite käyttää nykyistä positiivista control targetia ja fallbackina konfiguroitua surplus-tehoa.
- Yksi release per measurement-settle-jakso; n−1-release kirjoittaa uuden `surplus_freeze_s`-freezen.
- Viimeiseksi jäävä ensimmäisenä aktivoitu anchor käyttää edelleen `RPNZ <= 10 W` -release-sääntöä.
- Lisätty release-diagnostiikka: activation order, anchor, mode, power, margin, threshold ja excess consumption.

## Beta 1.1 — 2026-07-13

### HARD_OFF release semantics

- EV:n HARD_OFF-vapautuksen release-counter käyttää nyt vain peräkkäisiä PV-palautumistickejä.
- RPC ja surplus-laitteen activation threshold eivät enää osallistu lifecycle-vapautukseen.
- Vapautuminen tekee EV:stä vain jälleen eligible-laitteen; varsinainen käynnistys vaatii edelleen allocatorin RPC-, priority- ja active-state-ehdot.
- `activation_blocked` estää edelleen vapautumisen ja nollaa release-counterin.
- Korjattu samalla vanha kytkentä, jossa lifecycle `release_allowed` saattoi yksin muodostaa EV:lle aktiivisen surplus-DevicePolicyn.

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
