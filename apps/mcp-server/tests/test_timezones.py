import pytest
from bank_mcp.services.timezones import customer_timezone, ZONES

@pytest.mark.parametrize("location,expected",[
 ({"country":"México","state":"Baja California","city":"Tijuana"},"America/Tijuana"),
 ({"country":"Colombia","state":"Cundinamarca","city":"Bogotá"},"America/Bogota"),
 ({"country":"Argentina","state":"Córdoba","city":"Córdoba"},"America/Argentina/Cordoba"),
])
def test_location_resolution(location,expected):
 assert customer_timezone(location)==expected

@pytest.mark.parametrize("location",[{},{"country":"Mexico","state":"Unknown","city":"Unknown"}])
def test_unknown_location_is_not_silently_utc(location):
 with pytest.raises(ValueError): customer_timezone(location)
