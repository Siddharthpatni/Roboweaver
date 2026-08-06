import json

import pytest

from roboweaver.json_utils import loads_strict


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_loads_strict_rejects_non_standard_constants(constant):
    with pytest.raises(json.JSONDecodeError):
        loads_strict(f'{{"value":{constant}}}')


def test_loads_strict_accepts_standard_json():
    assert loads_strict('{"value":null,"ok":true}') == {"value": None, "ok": True}
