"""Tests for backend.server export presets and field selection"""
from backend.server import EXPORT_PRESETS, select_fields, resolve_export_fields


def test_all_presets_defined():
    expected = {"minimal", "clay", "apollo", "hubspot", "instantly", "n8n", "leads", "geo", "full"}
    assert set(EXPORT_PRESETS.keys()) == expected


def test_presets_have_fields():
    for name, fields in EXPORT_PRESETS.items():
        if name == "full":
            assert fields == []
        else:
            assert isinstance(fields, list)
            assert len(fields) > 0
            assert all(isinstance(f, str) for f in fields)


def test_select_fields_basic():
    places = [
        {"name": "A", "phone": "1", "extra": "remove"},
        {"name": "B", "phone": "2", "extra": "me"},
    ]
    result = select_fields(places, ["name", "phone"])
    assert result == [
        {"name": "A", "phone": "1"},
        {"name": "B", "phone": "2"},
    ]


def test_select_fields_missing_keys_become_none():
    places = [{"name": "A"}]
    result = select_fields(places, ["name", "phone"])
    assert result == [{"name": "A", "phone": None}]


def test_select_fields_empty_list_returns_unchanged():
    places = [{"name": "A", "extra": "keep"}]
    assert select_fields(places, None) == places
    assert select_fields(places, []) == places


def test_resolve_with_preset():
    fields = resolve_export_fields(preset="minimal")
    assert "name" in fields
    assert "phone" in fields
    assert "website" in fields


def test_resolve_with_custom_fields():
    fields = resolve_export_fields(fields=["foo", "bar"])
    assert fields == ["foo", "bar"]


def test_resolve_custom_overrides_preset():
    fields = resolve_export_fields(preset="minimal", fields=["custom_only"])
    assert fields == ["custom_only"]


def test_resolve_with_nothing_returns_none():
    assert resolve_export_fields() is None
