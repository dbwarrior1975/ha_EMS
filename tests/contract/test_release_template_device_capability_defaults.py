from pathlib import Path
import re

import pytest


@pytest.mark.unit
def test_release_runtime_templates_define_non_producer_minimum_for_relays(project_root):
    for filename in ('template.yaml', 'example_EMS_runtime_packet_sensors.yaml'):
        text = (Path(project_root) / filename).read_text(encoding='utf-8')
        for device_id in ('RELAY1', 'RELAY2'):
            match = re.search(
                rf"'{device_id}':\s*\{{\s*'capabilities':\s*\{{(?P<capabilities>.*?)\n\s*\}},\s*\n\s*'policy':\s*\{{",
                text,
                flags=re.DOTALL,
            )
            assert match is not None, f'{filename} missing runtime capability block for {device_id}'
            capabilities = match.group('capabilities')
            assert "'min_produce_w': 0" in capabilities, (
                f'{filename} {device_id} capabilities must explicitly define min_produce_w=0'
            )
            assert "'max_produce_w': 0" in capabilities, (
                f'{filename} {device_id} capabilities must explicitly define max_produce_w=0'
            )


@pytest.mark.unit
def test_release_runtime_template_revision_salt_tracks_static_config_change(project_root):
    for filename in ('template.yaml', 'example_EMS_runtime_packet_sensors.yaml'):
        text = (Path(project_root) / filename).read_text(encoding='utf-8')
        assert "{{ ((ns.latest * 1000000) | int) + 3 }}" in text
