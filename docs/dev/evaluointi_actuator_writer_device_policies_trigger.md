# Arviointi: actuator writerin trigger-lähde ja device_policies-sopimus

## Tiivistelmä

Suositus on **Option B: korvaa actuator writerin `policy_decision_trace`-state-trigger `device_policies`-state-triggerillä**, mutta vasta kun alla listatut trigger- ja idempotenssitestit on lisätty ja `device_policies`-sensorin state/attribuuttimuutosten triggeröityminen on varmistettu. Muutos kannattaa pitää pienenä trigger-sopimuksen muutoksena, ei laajempana pipeline-refaktorina.

Nykyinen toteutus on arkkitehtuurisesti väärään suuntaan kytkeytynyt, ei pelkästään kosmeettisesti suboptimaalinen: writerin kanoninen komentosopimus on `sensor.ems_device_policies_pyscript`, mutta writer käynnistyy tällä hetkellä `sensor.ems_policy_decision_trace_pyscript`-muutoksesta.

## Nykyhavainnot

Writerin triggerit ovat nyt:

```python
@time_trigger('period(now, 30s)')
@state_trigger(
    'sensor.ems_policy_decision_trace_pyscript or '
    'input_select.ems_control_profile'
)
```

Lähde: `ems_actuator_writers.py:456`.

Writer kuitenkin lukee device policyn ensin `sensor.ems_device_policies_pyscript`-sensorista ja vasta sen jälkeen fallbackina `sensor.ems_policy_decision_trace_pyscript`-sensorin `device_policies`-attribuutista. Lähde: `ems_actuator_writers.py:54`.

Policy engine julkaisee samat attrsit ensin `device_policies`-sensorille ja heti sen jälkeen `policy_decision_trace`-sensorille. Lähde: `ems_policy_engine.py:293`. Jos Pyscript/Home Assistant -tilapäivitysten ajoitus ei ole deterministinen writerin lukemisen näkökulmasta, trace-trigger voi käynnistää writerin hetkellä, jolloin varsinainen `device_policies`-sensorin uusi tila ei ole vielä writerin luettavissa. Tämä vastaa tuotannossa havaittua stale-read-ikkunaa.

Dokumentaatio tukee nykyistä tavoitearkkitehtuuria: actuator writer toimii kanonisesti `device_policies`-ulostulon perusteella ja EV:n writer-sopimus kulkee `device_policies[*].target_w`-arvona. Lähteet: `docs/dev/arkkitehtuuri.md:147` ja `docs/dev/arkkitehtuuri.md:524`.

Dispatch state applier on erillinen ja oikein trace-ohjattu komponentti: se lukee `policy_decision_trace`-attribuutteja ja triggeröityy trace-sensorista. Lähde: `ems_dispatch_state_applier.py:215`.

## Latenssivaikutus

`device_policies`-trigger vähentäisi todennäköisesti viimeisen osuuden latenssia:

```text
device_policies muuttuu -> actuator writer kirjoittaa
```

Tämä koskee seuraavia polkuja:

1. `RELAY1` / `RELAY2` päälle ja pois, kun `device_policies[*].enabled` muuttuu.
2. EV surplus päälle ja pois, kun `EV_CHARGER.target_w` tai `mode` muuttuu.
3. EV `target_w -> target_current_a` -muunnos writerissä.
4. `HOME_BATTERY.target_w`-muutos akun setpoint-kirjoitukseksi.

Muutos ei poista dispatch-arkkitehtuurin tietoista yhden kierroksen viivettä:

```text
dispatch_action -> active_surplus_devices -> seuraava policy -> device_policies
```

Tämä viive on kuvattu step-mallissa: policy laskee päätöksen stepin alun tilasta, dispatch muuttaa aktiivipinoa samassa stepissä, ja uusi vaikutus `device_policies`-ulostuloon näkyy tavallisesti vasta seuraavalla kierroksella. Lähde: `docs/dev/ems_step_model.md:21`.

E2E-testit vahvistavat tämän mallin. Esimerkiksi aktivointiketjussa `ACTIVATE_RELAY1` syntyy ensin, mutta `RELAY1.enabled=True` ja fyysinen relay näkyvät vasta seuraavassa vaiheessa. Lähde: `tests/e2e_entity/net_zero_priority_order_quarter/test_01_activation_chain.py:14`. Vastaavasti release-ketjussa `RELEASE_RELAY2` muuttaa aktiivipinoa ennen kuin `RELAY2.enabled=False` näkyy seuraavassa policyssä. Lähde: `tests/e2e_entity/net_zero_priority_order_quarter/test_02_release_relay2_then_adjustable.py:58`.

Johtopäätös: trigger-muutos ei lyhennä dispatch-päätöksen semanttista viivettä, mutta poistaa turhan epädeterministisyyden siitä hetkestä, kun uusi writer-komento on jo julkaistu `device_policies`-sensorille.

## Riskit ja sivuvaikutukset

Writerit ovat pääosin idempotentteja:

1. Relay kirjoittaa vain jos haluttu tila eroaa nykytilasta, muuten palauttaa `already_matching`. Lähde: `ems_actuator_writers.py:410`.
2. EV enable/current kirjoitetaan vain jos enable-tila tai current-arvo muuttuu. Lähde: `ems_actuator_writers.py:270`.
3. EV restore/hard_off -polut vertaavat currentia ja enable-tilaa ennen kirjoitusta. Lähde: `ems_actuator_writers.py:288`.
4. Akkuwriter käyttää deadbandia ja ramp-rajaa, joten identtinen tai hyvin pieni target-muutos ei aiheuta jatkuvaa kirjoitusta. Lähde: `ems_actuator_writers.py:169`.

Suurin riski ei ole service-call-spam vaan startup/reload- ja fallback-käyttäytyminen. Nykyinen fallback trace-sensorin `device_policies`-attribuuttiin voi peittää tilanteita, joissa varsinainen `device_policies`-sensori puuttuu tai on hetkellisesti vanha. Jos trace-trigger poistetaan, writer ei enää herää pelkkään trace-muutokseen. Varalla jäävät 30 sekunnin periodinen trigger ja `input_select.ems_control_profile`.

Manual/off/control profile -siirtymät näyttävät turvallisilta, koska control profile säilyy writerin triggerinä ja battery writer ohittaa MANUAL-tilassa kirjoituksen suoraan. Lähde: `ems_actuator_writers.py:120`.

Trace-only-muutosten ei pitäisi jatkossa kirjoittaa aktuaattoreita. Se on arkkitehtuurisesti oikein, koska `policy_decision_trace` on diagnostiikka- ja dispatch-selityspinta, ei writerin komentolähde.

## Suositeltu toteutuspolku

1. Lisää ensin testit, jotka lukitsevat trigger-sopimuksen ja idempotenssin.
2. Tee pieni trigger-only-muutos:

```python
@time_trigger('period(now, 30s)')
@state_trigger(
    'sensor.ems_device_policies_pyscript or '
    'input_select.ems_control_profile'
)
def ems_actuator_writers_loop():
    ...
```

3. Jätä `_device_policy_by_id`-fallback trace-attribuuttiin aluksi paikalleen startup/reload-yhteensopivuuden vuoksi, mutta älä käytä tracea writerin päätriggerinä.
4. Aja unit- ja skenaariotestit.
5. Poista trace-fallback erillisessä siivouksessa vain, jos testit ja tuotantohavainnot osoittavat, ettei sitä enää tarvita.

Option A eli molempien triggerien väliaikainen pitäminen on hyväksyttävä vain lyhyenä riskinpoistovaiheena. Se vähentää stale-read-riskiä, mutta pitää väärän diagnostisen kytkennän elossa ja voi piilottaa jäljelle jääviä sopimusongelmia. Option C ei vastaa nykyarkkitehtuuria eikä tuotantohavaintoa.

## Tarvittavat testit ennen muutosta

Lisää vähintään nämä testit:

1. `test_writer_state_trigger_uses_device_policies_not_policy_trace`: lataa writer-moduuli testidekoraattorilla, joka tallentaa `@state_trigger`-argumentin, ja varmista että siinä on `sensor.ems_device_policies_pyscript` eikä `sensor.ems_policy_decision_trace_pyscript`.
2. `test_writer_reacts_when_only_device_policies_changes`: simuloi `device_policies`-muutos `RELAY1.enabled False -> True` ilman trace-muutosta ja varmista, että writer kääntää releen päälle.
3. `test_writer_trace_only_change_does_not_override_device_policies`: anna `device_policies`-sensorille uusi tai nykyinen kanoninen komento ja trace-fallbackille ristiriitainen `device_policies`; varmista, että kanoninen `device_policies` voittaa.
4. `test_writer_repeated_identical_device_policies_does_not_rewrite_relay_or_ev`: aja writer kahdesti samoilla policyillä ja varmista, että toinen ajo palauttaa `written=False` / `already_matching` tai vastaavan skip-syyn.
5. `test_writer_ev_current_update_from_device_policies_is_idempotent`: muuta `EV_CHARGER.target_w` niin, että laskettu current muuttuu, ja varmista yksi `number.set_value`; toinen ajo samalla targetilla ei kirjoita uudelleen.
6. `test_writer_battery_target_update_from_device_policies_is_idempotent`: muuta `HOME_BATTERY.target_w`, varmista uusi setpoint ja toistolla deadband/ei-uusintakirjoitusta.
7. Skenaariotestien smoke: aja ainakin `net_zero_priority_order_quarter`, `net_zero_priority_order_quarter_3_relays`, `net_zero_force_on_battery_support` ja `hard_off_on_low_pv`, koska ne kattavat activation/release-, force-on- ja hard_off-polut.

## Avoimet kysymykset

1. Tarvitaanko trace-fallbackia `_device_policy_by_id`-funktiossa enää tuotannon reload/startup-tilanteissa, vai pitäisikö missing `device_policies` tehdä näkyväksi virheeksi writer tracessa?
2. Onko Home Assistant/Pyscript -ympäristössä mahdollista saada `device_policies`-state-trigger tilanteessa, jossa vain attribuutit muuttuvat mutta state-arvo pysyy samana? Nykyinen policy engine julkaisee stateksi policyjen lukumäärän, joten jos vain attribuuttisisältö muuttuu ja lukumäärä pysyy samana, tämä on kriittinen varmistettava kohta.
3. Jos attribuuttimuutos ei laukaise state-triggeriä, `sensor.ems_device_policies_pyscript`-sensorin state-arvo pitää muuttaa esimerkiksi versioksi, hashiksi tai timestampiksi. Ilman tätä pelkkä triggerin vaihtaminen voi jättää writerin edelleen 30 sekunnin periodisen triggerin varaan.
4. Pitäisikö writer traceen lisätä `policy_source_entity`, jotta tuotannossa nähdään suoraan, luettiinko komento `device_policies`-sensorista vai fallback-tracesta?

## Päätös

Nykyinen writer trigger -lähde on arkkitehtuurisesti väärä suhteessa puhtaaseen device-pipelineen. `device_policies` on komentorajapinta, `policy_decision_trace` on diagnostiikka ja dispatch-selitys.

Suositeltu muutos on pieni trigger-only-korjaus, ei laajempi pipeline-refaktori. Tärkein varmistus ennen toteutusta on, että `sensor.ems_device_policies_pyscript` todella triggeröityy jokaisesta actuator-relevantista policy-muutoksesta myös silloin, kun sensorin state-arvo eli policyjen lukumäärä ei muutu.
