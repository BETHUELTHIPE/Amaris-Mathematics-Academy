"""Offline GeoNames lookups; location metadata never grants account permissions."""

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

from rest_framework import serializers

DATA = Path(__file__).with_name("data") / "locations"
COUNTRIES = json.loads((DATA / "index.json").read_text())
COUNTRY_CHOICES = [(country["code"], country["name"]) for country in COUNTRIES]
COUNTRY_NAMES = dict(COUNTRY_CHOICES)
OTHER = "__other__"


@lru_cache(maxsize=64)
def country_data(code):
    if code not in COUNTRY_NAMES:
        return None
    return json.loads((DATA / (code + ".json")).read_text())


def normalize_location(attrs):
    """Allow legacy clients without location fields; validate every supplied location."""
    keys = ("country", "province", "city", "provinceOther", "cityOther")
    if not any(key in attrs for key in keys):
        return attrs
    raw = {key: unicodedata.normalize("NFC", str(attrs.get(key, "")).strip()) for key in keys}
    data = country_data(raw["country"])
    errors = {}
    if not raw["country"]:
        errors["country"] = "Please choose your country."
    elif not data:
        errors["country"] = "Please choose an African country from the list."
    if not raw["province"]:
        errors["province"] = "Please choose your province or region."
    elif raw["province"] == OTHER:
        if not raw["provinceOther"] or len(raw["provinceOther"]) > 160:
            errors["provinceOther"] = "Please enter your province or region."
    elif not data or raw["province"] not in data["provinces"]:
        errors["province"] = "Please choose a province or region in your selected country."
    if not raw["city"]:
        errors["city"] = "Please choose your city or town."
    elif raw["city"] == OTHER:
        if not raw["cityOther"] or len(raw["cityOther"]) > 160:
            errors["cityOther"] = "Please enter your city or town."
    elif not data or raw["city"] not in data["provinces"].get(raw["province"], []):
        errors["city"] = "Please choose a city or town in your selected province."
    if errors:
        raise serializers.ValidationError(errors)
    attrs["country"] = raw["country"]
    attrs["province"] = raw["provinceOther"] if raw["province"] == OTHER else raw["province"]
    attrs["city"] = raw["cityOther"] if raw["city"] == OTHER else raw["city"]
    attrs.pop("provinceOther", None)
    attrs.pop("cityOther", None)
    return attrs
