from datetime import datetime, timedelta

from pydantic import BaseModel

from vencar.utils.hashing import sha256_hex
from vencar.utils.ids import new_id
from vencar.utils.serialization import to_json, to_plain_data
from vencar.utils.text import split_csv
from vencar.utils.time import utc_now


class Sample(BaseModel):
    """Small model used to test conversions."""

    name: str


def test_utc_now_is_iso_8601_in_utc() -> None:
    """The timestamp can be parsed and has no offset from UTC."""
    assert datetime.fromisoformat(utc_now()).utcoffset() == timedelta(0)


def test_new_id_is_unique() -> None:
    """Two identifiers are never the same."""
    assert new_id() != new_id()


def test_sha256_hex_matches_a_known_digest() -> None:
    """The digest of a known text does not change."""
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    assert sha256_hex("abc") == expected


def test_to_json_keeps_accents_and_handles_unknown_types() -> None:
    """Accented text stays readable and unknown types become text."""
    assert to_json({"nome": "Goiânia", "data": timedelta(0)}) == (
        '{"nome": "Goiânia", "data": "0:00:00"}'
    )


def test_to_plain_data_converts_only_models() -> None:
    """Models become dictionaries and other values stay the same."""
    assert to_plain_data(Sample(name="x")) == {"name": "x"}
    assert to_plain_data([1, 2]) == [1, 2]


def test_split_csv_drops_spaces_and_empty_items() -> None:
    """Spaces and empty items are removed."""
    assert split_csv(" a, b ,,c ") == ["a", "b", "c"]
