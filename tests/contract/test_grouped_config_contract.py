import pytest

from ems_adapter.config_loader import load_grouped_ems_config, validate_grouped_ems_config








@pytest.mark.unit
def test_grouped_config_rejects_unknown_fields_in_active_contract(project_root):
    config = load_grouped_ems_config(project_root / 'example_EMS_config.yaml')
    config['ems']['devices']['EV_CHARGER']['adapter']['unexpected_field'] = 'input_number.foo'

    result = validate_grouped_ems_config(config)

    assert result.ok is False
    assert any(
        issue.path == 'ems.devices.EV_CHARGER.adapter.unexpected_field'
        and issue.message == 'Unknown config field: ems.devices.EV_CHARGER.adapter.unexpected_field'
        for issue in result.errors
    )
