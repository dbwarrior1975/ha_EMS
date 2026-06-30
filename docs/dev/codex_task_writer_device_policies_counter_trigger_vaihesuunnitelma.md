# Vaihesuunnitelma: device_policies-counter ja actuator writerin trigger-korjaus

## Arvio lähestymistavasta

Päivitetyn taskin lähestymistapa on validi ja korjaa aiemman arvioinnin keskeisen avoimen riskin: `sensor.ems_device_policies_pyscript` ei saa käyttää state-arvona policyjen lukumäärää, koska actuator-komennot muuttuvat usein policy-listan pituuden pysyessä samana. Counter-/version-state on oikea tapa varmistaa, että Home Assistant/Pyscript state-trigger laukeaa myös esimerkiksi `RELAY1.enabled false -> true`, `EV_CHARGER.target_w 0 -> 1840` ja `HOME_BATTERY.target_w 0 -> -500` -muutoksissa.

Nykykoodi tukee tätä arviota:

1. Policy engine julkaisee device policy -sensorin stateksi nyt policyjen lukumäärän: `publish_sensor(entities['device_policies'], len(attrs.get('device_policies', ())), attrs)` tiedostossa `ems_policy_engine.py`.
2. Actuator writerin state-trigger on edelleen `sensor.ems_policy_decision_trace_pyscript or input_select.ems_control_profile` tiedostossa `ems_actuator_writers.py`.
3. Writer lukee komennon ensisijaisesti `sensor.ems_device_policies_pyscript`-sensorilta ja fallbackina trace-sensorilta. Tämä fallback voidaan jättää aluksi paikalleen, mutta triggeri pitää siirtää kanoniseen sensorin.

Toteutus kannattaa pitää pienenä trigger-contract-korjauksena. Älä muuta dispatch pipelinea, policy-laskentaa, EV watt-native -mallia, hard_off/restore_min-semanttiikkaa tai yhden laitteen per sykli aktivointi-/release-mallia.

## Suositeltu toteutusjärjestys

### Vaihe 1: Lisää policy engineen device_policies-version helper

Muokattava tiedosto: `ems_policy_engine.py`.

Lisää moduulitasolle laskuri:

```python
_DEVICE_POLICIES_VERSION = 0
```

Lisää helper, joka kasvattaa laskuria ja julkaisee device policy -sensorin counter-state-arvolla:

```python
def _publish_device_policies(entity_id, attrs):
    global _DEVICE_POLICIES_VERSION
    _DEVICE_POLICIES_VERSION += 1
    publish_sensor(entity_id, str(_DEVICE_POLICIES_VERSION), attrs)
    return str(_DEVICE_POLICIES_VERSION)
```

Ensimmäisessä toteutuksessa kasvata laskuria jokaisella policy engine -julkaisulla. Tämä on turvallinen, koska writer on idempotentti ja 30 sekunnin periodinen trigger on jo olemassa. Sisältöhashiin perustuva optimointi voidaan tehdä myöhemmin, jos writer trace -melu osoittautuu ongelmaksi.

Korvaa nykyinen rivi:

```python
publish_sensor(entities['device_policies'], len(attrs.get('device_policies', ())), attrs)
```

muodolla:

```python
device_policies_version = _publish_device_policies(entities['device_policies'], attrs)
```

Lisää sama version tieto mielellään attrs-diagnostiikkaan ennen julkaisua:

```python
attrs['device_policies_version'] = next_version
```

Käytännöllisempi helper-rakenne on:

```python
def _next_device_policies_version():
    global _DEVICE_POLICIES_VERSION
    _DEVICE_POLICIES_VERSION += 1
    return str(_DEVICE_POLICIES_VERSION)
```

Silloin loopissa:

```python
device_policies_version = _next_device_policies_version()
attrs['device_policies_version'] = device_policies_version
publish_sensor(entities['device_policies'], device_policies_version, attrs)
```

Tämä pitää version näkyvissä sekä sensorin state-arvossa että attribuuteissa.

### Vaihe 2: Vaihda actuator writerin state-trigger

Muokattava tiedosto: `ems_actuator_writers.py`.

Vaihda:

```python
@state_trigger(
    'sensor.ems_policy_decision_trace_pyscript or '
    'input_select.ems_control_profile'
)
```

muotoon:

```python
@state_trigger(
    'sensor.ems_device_policies_pyscript or '
    'input_select.ems_control_profile'
)
```

Pidä `@time_trigger('period(now, 30s)')` safety netinä.

Älä muuta `ems_dispatch_state_applier.py` triggeriä. Dispatch applierin kuuluu edelleen triggeröityä `policy_decision_trace`-sensorista, koska dispatch-päätös elää trace-attribuuteissa.

### Vaihe 3: Lisää writerin lähdediagnostiikka

Muokattava tiedosto: `ems_actuator_writers.py`.

Nykyinen `_device_policy_by_id` palauttaa vain policyn, ei tietoa siitä, mistä sensorista policy löytyi. Lisää pieni apufunktio tai laajenna palautusmuoto hallitusti.

Vähäriskinen vaihtoehto:

1. Lisää `_device_policy_source_for_id(device_id, entities=None)`, joka käy samat lähteet läpi kuin `_device_policy_by_id` ja palauttaa tuple-muodon `(policy, source_entity, source_reason)`.
2. Muuta `_device_policy_by_id` käyttämään uutta helperiä ja palauttamaan vain `policy`, jotta olemassa olevat kutsut eivät hajoa.
3. Lisää writer traceen yleinen diagnostiikka:

```python
'policy_source_entity': _ent('device_policies', 'sensor.ems_device_policies_pyscript', entities),
'policy_source_reason': 'canonical',
'device_policies_version': get_str(_ent('device_policies', 'sensor.ems_device_policies_pyscript', entities), ''),
```

Jos halutaan tarkasti raportoida fallback, device-kohtaisiin traceihin voi lisätä:

```python
'policy_source_entity': source_entity,
'policy_source_reason': 'canonical' tai 'fallback_device_policies_missing',
```

Pidä olemassa oleva `policy_source: device_policy` ennallaan, koska testit käyttävät sitä. Lisää uudet kentät sen rinnalle.

### Vaihe 4: Lisää trigger-sopimustestit

Muokattava tiedosto: `tests/unit/test_writer_semantics.py`.

Nykyinen `_load_writer_module` käyttää testidekoraattoria, joka ei tallenna `@state_trigger`-argumentteja. Päivitä se keräämään triggerit esimerkiksi näin:

```python
trigger_calls = []

def _state_trigger(*args, **kwargs):
    trigger_calls.append(('state', args, kwargs))
    def deco(fn):
        return fn
    return deco
```

Palauta `trigger_calls` joko moduulin namespaceen tai erillisenä paluuarvona. Jos paluuarvon muuttaminen aiheuttaa liikaa testimuutoksia, lisää namespaceen:

```python
'_TEST_TRIGGER_CALLS': trigger_calls,
```

Lisää testi:

```text
test_writer_state_trigger_uses_device_policies_not_policy_trace
```

Odotukset:

1. `sensor.ems_device_policies_pyscript` löytyy writerin state-triggeristä.
2. `sensor.ems_policy_decision_trace_pyscript` ei löydy writerin state-triggeristä.
3. `input_select.ems_control_profile` säilyy triggerissä.

### Vaihe 5: Lisää policy engine -julkaisutestit counterille

Sopiva paikka: `tests/contract/test_grouped_config_runtime_parity.py` tai uusi unit-/contract-testi, joka käyttää `QuarterScenarioHarness`-harnessia.

Lisää testi:

```text
test_device_policies_sensor_state_is_version_not_policy_count
```

Testin idea:

1. Aja `h.step(...)`.
2. Lue `device_policies_entity = E['device_policies']`.
3. Tallenna `first_state = h.get(device_policies_entity)`.
4. Muuta actuator-relevanttia inputtia niin, että policy-listan määrä pysyy samana mutta sisältö muuttuu.
5. Aja uusi step.
6. Varmista `second_state != first_state`.
7. Varmista `second_state != len(h.getattrs(device_policies_entity)['device_policies'])`, jos halutaan eksplisiittisesti torjua policy count -regressio.

Minimikattavuus:

1. `RELAY1.enabled false -> true`: käytä force-onia tai skenaariota, jossa active surplus tuottaa RELAY1-policyyn enabled-muutoksen.
2. `EV_CHARGER.target_w` muuttuu: käytä EV surplus- tai EV force-on -polkua.
3. `HOME_BATTERY.target_w` muuttuu: muuta net zero / battery target -inputteja niin, että battery policy target muuttuu.

Jos tarkka policy-sisältömuutos on hankala rakentaa yhdessä testissä, hyväksy alkuun yleisempi testi: kaksi peräkkäistä policy loop -julkaisua kasvattaa counteria, vaikka device policyjen määrä pysyy samana.

### Vaihe 6: Lisää canonical-vs-fallback-testit writerille

Muokattava tiedosto: `tests/unit/test_writer_semantics.py`.

Nykyinen `_install_device_policies` palauttaa samat policies kaikille source-entityille. Lisää helper, jolla voi asentaa eri policyt eri sensoreille:

```python
def _install_device_policies_by_entity(mod, mapping):
    def get_attr(entity_id, attr, default=None):
        if attr == 'device_policies':
            return tuple(mapping.get(entity_id, ()))
        return default
    mod['get_attr'] = get_attr
```

Lisää testi:

```text
test_writer_uses_canonical_device_policies_before_trace_fallback
```

Asetelma:

1. `sensor.ems_device_policies_pyscript` sanoo `RELAY1.enabled=True`.
2. `sensor.ems_policy_decision_trace_pyscript` sanoo `RELAY1.enabled=False`.
3. Rele on aluksi pois.
4. Writer ajaa.
5. Odota, että rele kääntyy päälle.

Lisää testi:

```text
test_writer_can_still_use_trace_fallback_when_canonical_missing
```

Asetelma:

1. Canonical sensorilla ei ole `device_policies`-attribuuttia.
2. Trace fallback sisältää validin `RELAY1.enabled=True`.
3. Writer ajaa.
4. Odota, että rele kääntyy päälle ja trace kertoo fallback-lähteen, jos diagnostiikka toteutettiin.

### Vaihe 7: Lisää idempotenssitestit service-call-spamin estoon

Muokattava tiedosto: `tests/unit/test_writer_semantics.py`.

Nykyiset fake `set_boolean` ja `set_number` tallentavat vain state-arvon. Lisää call log:

```python
calls = []

def set_boolean(entity_id, on):
    calls.append(('set_boolean', entity_id, bool(on)))
    state[entity_id] = bool(on)

def set_number(entity_id, value):
    calls.append(('set_number', entity_id, value))
    state[entity_id] = value
```

Palauta call log namespaceen esimerkiksi `'_TEST_CALLS': calls`.

Lisää testit:

1. `test_writer_repeated_identical_relay_policy_does_not_repeat_service_call`.
2. `test_writer_repeated_identical_ev_current_policy_does_not_repeat_service_call`.
3. `test_writer_repeated_identical_battery_policy_respects_deadband_without_repeat_write`.

Ole tarkkana akun kanssa: jos current setpoint ei ole deadbandin sisällä tai ramp aiheuttaa useamman askeleen, writer voi tarkoituksella kirjoittaa useamman kerran. Testaa idempotenssi niin, että ensimmäisen ajon jälkeen current on täsmälleen targetissa tai deadbandin sisällä.

### Vaihe 8: Päivitä dokumentaatio lyhyesti

Muokattavat tiedostot tarpeen mukaan:

1. `docs/dev/arkkitehtuuri.md`: mainitse, että `sensor.ems_device_policies_pyscript` state on version/counter ja attrs sisältävät varsinaisen `device_policies`-payloadin.
2. `docs/user/operointi.md` tai `docs/user/releasenotes.md`: mainitse käyttäjälle näkyvä muutos, jos sensorin state-arvo muuttuu policyjen määrästä versionumeroksi.

Pidä dokumentaatiomuutos lyhyenä. Älä laajenna samalla vanhoja arkkitehtuuriosioita.

## Testiajo seuraavassa sessiossa

Minimiajo:

```bash
pytest -q tests/unit/test_writer_semantics.py
pytest -q tests/contract/test_grouped_config_runtime_parity.py
```

Skenaarioajo:

```bash
pytest -q tests/e2e_entity/net_zero_priority_order_quarter/
pytest -q tests/e2e_entity/net_zero_priority_order_quarter_3_relays/
pytest -q tests/e2e_entity/net_zero_force_on_battery_support/
pytest -q tests/e2e_entity/hard_off_on_low_pv/
pytest -q tests/e2e_entity/net_zero_ev_adjustable_load/
```

Jos aika riittää:

```bash
pytest -q
```

## Hyväksymiskriteerit

1. `sensor.ems_device_policies_pyscript` state ei ole enää policyjen lukumäärä.
2. `sensor.ems_device_policies_pyscript` state muuttuu policy engine -julkaisuissa counter-/version-arvoksi.
3. Actuator writerin state-trigger sisältää `sensor.ems_device_policies_pyscript`.
4. Actuator writerin state-trigger ei sisällä `sensor.ems_policy_decision_trace_pyscript`.
5. Writer lukee canonical `device_policies` -sensorin ennen trace-fallbackia.
6. Writer trace kertoo ainakin yleistasolla device policy -version ja mieluiten canonical/fallback-lähteen.
7. Toistuvat writer-ajot identtisellä halutulla actuator-tilalla eivät tee uusia `set_boolean`- tai `set_number`-kutsuja.
8. E2E-skenaariot osoittavat, ettei dispatchin yhden syklin semantiikka muuttunut.

## Riskit ja rajaukset

1. Counterin kasvattaminen jokaisella policy-julkaisulla voi lisätä writer-loopin ajoja. Tämä on hyväksyttävä ensimmäisessä vaiheessa, koska writerin pitää olla idempotentti.
2. Jos tuotannossa Pyscript reload nollaa moduulitason counterin, state voi palata pienempään arvoon. Tämä on hyväksyttävää triggeröinnin kannalta, koska state muuttuu silti.
3. Älä toteuta tässä vaiheessa sisältöhashia, ellei counter joka julkaisulla aiheuta todellista ongelmaa.
4. Älä poista trace-fallbackia vielä. Sen poistaminen on erillinen cleanup, kun startup/reload-käyttäytyminen on nähty tuotannossa.
5. Älä muuta `policy_decision_trace`-sensorin sisältöä tai dispatch applierin triggeriä.

## PR-yhteenveto seuraavalle sessiolle

```text
Switch actuator writer triggering to the canonical device_policies sensor.

device_policies now publishes a monotonically increasing version as sensor state,
so state triggers fire even when actuator-relevant policy content changes without
changing the number of policies. The writer no longer uses policy_decision_trace
as its normal trigger, but keeps the 30s reconciliation trigger and temporary
trace fallback for startup/reload compatibility.
```
