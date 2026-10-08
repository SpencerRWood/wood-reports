from dataclasses import replace
from typing import Any

import pytest

from wood_reports import (
    ProfileSection,
    ProfileValidationError,
    get_profile,
    list_profiles,
)


def test_initial_profiles_are_versioned_typed_and_semantically_distinct() -> None:
    profiles = list_profiles()
    assert {profile.identity for profile in profiles} == {
        "project-brief",
        "analytics-report",
        "assessment-report",
        "decision-memo",
        "technical-architecture",
    }
    assert all(profile.version == "1.0.0" for profile in profiles)
    assert "what the data shows" in get_profile("analytics-report").purpose
    assert "current state" in get_profile("assessment-report").purpose
    assert (
        get_profile("analytics-report").section("KPI Overview").identity
        == "key-metrics"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"identity": ""},
        {"identity": "Bad Identity"},
        {"display_name": ""},
        {"purpose": ""},
        {"version": ""},
        {"required_metadata": ("title",)},
        {"optional_metadata": ("title",)},
        {"optional_metadata": ("client", "client")},
        {"callouts": ("",)},
        {"permitted_content": ("latex",)},
        {"sections": (ProfileSection("risk", "Risk", ""),)},
        {"sections": (ProfileSection("Bad Identity", "Risk", "Guidance"),)},
        {
            "sections": (
                ProfileSection("risk", "Risk", "Guidance"),
                ProfileSection("risk", "Other", "Guidance"),
            )
        },
        {"sections": (ProfileSection("risk", "Risk", "Guidance", ("Risk",)),)},
        {"required_section_variants": ()},
        {"required_section_variants": (("unknown",),)},
        {"required_section_variants": (("decision", "decision"),)},
    ],
)
def test_invalid_profile_contracts_fail_before_use(changes: dict[str, Any]) -> None:
    profile = replace(get_profile("decision-memo"), **changes)
    with pytest.raises(ProfileValidationError):
        profile.validate_schema()


def test_instance_identity_must_match_the_selected_profile() -> None:
    profile = get_profile("decision-memo")
    with pytest.raises(ProfileValidationError, match="does not match"):
        profile.validate_instance(
            {
                "doc_type": "assessment-report",
                "doc_name": "valid-slug",
                "title": "Title",
            },
            profile.required_section_variants[0],
        )
