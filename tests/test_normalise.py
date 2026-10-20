import pytest

from normalise.fields import (
    norm_clinician,
    norm_date,
    norm_flag,
    norm_name,
    norm_number,
    norm_range,
    norm_sex,
)


@pytest.mark.parametrize(
    "text",
    ["06/03/1964", "06.03.1964", "1964-03-06", "06 Mar 1964", "6 mars 1964", "06 March 1964"],
)
def test_every_date_style_becomes_iso(text: str) -> None:
    assert norm_date(text) == "1964-03-06"


def test_french_month_with_accent() -> None:
    assert norm_date("14 février 1965") == "1965-02-14"


def test_impossible_date_is_left_to_fail_matching() -> None:
    assert norm_date("31/02/2024") == "31/02/2024"


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("3,5 - 5,1", "3.5-5.1"),
        ("136 - 145", "136.0-145.0"),
        ("> 60", "60.0-"),
        ("≤ 200", "-200.0"),
    ],
)
def test_ranges_match_the_label_format(text: str, want: str) -> None:
    assert norm_range(text) == want


def test_numbers_flags_and_sex() -> None:
    assert norm_number("12,7") == "12.7"
    assert [norm_flag(f) for f in ["Haut", "↑", "High", "B", "Bas", "↓"]] == ["H"] * 3 + ["L"] * 3
    assert [norm_sex(s) for s in ["Féminin", "Male", "M"]] == ["F", "M", "M"]


@pytest.mark.parametrize("text", ["Chauvin, Anne", "CHAUVIN Anne", "Anne Chauvin"])
def test_name_orders_become_given_family(text: str) -> None:
    assert norm_name(text).casefold() == "anne chauvin"


def test_compound_upper_family_name() -> None:
    assert norm_name("LE GOFF Marie-Anne") == "Marie-Anne LE GOFF"


def test_clinician_titles_are_dropped() -> None:
    assert norm_clinician("Dr. Kwame Boateng") == "Kwame Boateng"
    assert norm_clinician("Docteur  Anne Petit") == "Anne Petit"
