"""Versioned semantic document contracts owned by Wood Reports."""

from __future__ import annotations

import re
from dataclasses import dataclass


class ProfileValidationError(ValueError):
    """An invalid profile definition or document instance."""


def semantic_id(value: str) -> str:
    """Normalize a display heading into its stable semantic identifier."""
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


@dataclass(frozen=True, slots=True)
class ProfileSection:
    identity: str
    title: str
    guidance: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentProfile:
    identity: str
    display_name: str
    purpose: str
    version: str
    required_metadata: tuple[str, ...]
    optional_metadata: tuple[str, ...]
    sections: tuple[ProfileSection, ...]
    required_section_variants: tuple[tuple[str, ...], ...]
    permitted_content: tuple[str, ...]
    callouts: tuple[str, ...]
    authored_sections: bool = False

    def validate_schema(self) -> None:  # noqa: PLR0912
        """Reject malformed contracts before authoring or instance validation."""
        for field, value in (
            ("identity", self.identity),
            ("display_name", self.display_name),
            ("purpose", self.purpose),
            ("version", self.version),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ProfileValidationError(f"profile.{field}: must be nonblank text")
        if semantic_id(self.identity) != self.identity:
            raise ProfileValidationError("profile.identity: must be a semantic slug")
        for field, values in (
            ("required_metadata", self.required_metadata),
            ("optional_metadata", self.optional_metadata),
            ("permitted_content", self.permitted_content),
            ("callouts", self.callouts),
        ):
            if (
                not isinstance(values, tuple)
                or not all(isinstance(value, str) and value.strip() for value in values)
                or len(values) != len(set(values))
            ):
                raise ProfileValidationError(f"profile.{field}: requires unique text")
        if not {"doc_type", "doc_name", "title"}.issubset(self.required_metadata):
            raise ProfileValidationError(
                "profile.required_metadata: missing identity fields"
            )
        if set(self.required_metadata) & set(self.optional_metadata):
            raise ProfileValidationError(
                "profile.metadata: required and optional overlap"
            )
        if not set(self.permitted_content) <= {
            "prose",
            "list",
            "table",
            "chart",
            "callout",
            "heading",
            "code",
            "diagram",
        }:
            raise ProfileValidationError(
                "profile.permitted_content: unsupported content"
            )
        identities: set[str] = set()
        headings: set[str] = set()
        for section in self.sections:
            if not isinstance(section, ProfileSection) or not section.guidance.strip():
                raise ProfileValidationError(
                    "profile.sections: requires typed section guidance"
                )
            if (
                not section.identity
                or semantic_id(section.identity) != section.identity
            ):
                raise ProfileValidationError(
                    "profile.sections: invalid section identity"
                )
            if section.identity in identities:
                raise ProfileValidationError("profile.sections: duplicate identity")
            identities.add(section.identity)
            for heading in (section.title, *section.aliases):
                key = semantic_id(heading)
                if not key or key in headings:
                    raise ProfileValidationError("profile.sections: ambiguous heading")
                headings.add(key)
        if not self.required_section_variants or any(
            not variant
            or len(set(variant)) != len(variant)
            or not set(variant) <= identities
            for variant in self.required_section_variants
        ):
            raise ProfileValidationError("profile.sections: invalid required variant")

    def section(self, heading: str) -> ProfileSection:
        for section in self.sections:
            if semantic_id(heading) in {
                semantic_id(value) for value in (section.title, *section.aliases)
            }:
                return section
        if self.authored_sections and semantic_id(heading):
            return ProfileSection(
                semantic_id(heading), heading, "Source-owned architecture section."
            )
        raise ProfileValidationError(
            f"sections.{heading}: unrecognized profile heading"
        )

    def validate_instance(
        self, metadata: dict[str, str], sections: tuple[str, ...]
    ) -> None:
        for name in self.required_metadata:
            if not metadata.get(name, "").strip():
                raise ProfileValidationError(f"frontmatter.{name}: is required")
        unknown = metadata.keys() - set(self.required_metadata + self.optional_metadata)
        if unknown:
            raise ProfileValidationError(
                f"frontmatter: unsupported fields {sorted(unknown)}"
            )
        if metadata["doc_type"] != self.identity:
            raise ProfileValidationError("frontmatter.doc_type: does not match profile")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", metadata["doc_name"]):
            raise ProfileValidationError(
                "frontmatter.doc_name: requires a lowercase slug"
            )
        duplicate_sections = {
            identity for identity in sections if sections.count(identity) > 1
        }
        defined_sections = {section.identity for section in self.sections}
        if duplicate_sections and (
            not self.authored_sections or duplicate_sections & defined_sections
        ):
            raise ProfileValidationError("sections: duplicate semantic section")
        if not any(
            set(variant) <= set(sections) for variant in self.required_section_variants
        ):
            missing = [
                sorted(set(variant) - set(sections))
                for variant in self.required_section_variants
            ]
            raise ProfileValidationError(
                f"sections: missing required sections; alternatives {missing}"
            )


_METADATA = (
    "subtitle",
    "author",
    "source",
    "client",
    "project",
    "engagement",
    "version",
    "audience",
    "confidentiality",
    "period",
    "comparison_period",
)
_CONTENT = ("prose", "list", "table", "chart", "callout", "heading", "code")
_CALLOUTS = (
    "summary",
    "finding",
    "recommendation",
    "risk",
    "decision",
    "metric",
    "note",
)


def _section(title: str, guidance: str, *aliases: str) -> ProfileSection:
    return ProfileSection(semantic_id(title), title, guidance, aliases)


def _profile(
    identity: str,
    purpose: str,
    sections: tuple[ProfileSection, ...],
    required: tuple[tuple[str, ...], ...],
) -> DocumentProfile:
    return DocumentProfile(
        identity,
        identity.replace("-", " ").title(),
        purpose,
        "1.0.0",
        ("doc_type", "doc_name", "title"),
        _METADATA,
        sections,
        required,
        _CONTENT,
        _CALLOUTS,
    )


_PROFILES = (
    DocumentProfile(
        identity="technical-architecture",
        display_name="Technical Architecture",
        purpose=(
            "Preserve canonical architecture facts, diagrams and evidence "
            "in a technical publication."
        ),
        version="1.0.0",
        required_metadata=("doc_type", "doc_name", "title"),
        optional_metadata=(*_METADATA, "toc", "page_layout"),
        sections=tuple(
            _section(title, guidance)
            for title, guidance in (
                (
                    "Summary",
                    "Describe the authored architecture scope "
                    "and evidence limitations.",
                ),
                ("Architecture Context", "Present system context and boundaries."),
                ("Components", "Present authored components and technical inventory."),
                ("Dependencies", "Present typed directed dependency relationships."),
                ("Orchestration", "Present authored orchestration relationships."),
                (
                    "Deployment",
                    "Present declared deployment topology "
                    "without attesting runtime health.",
                ),
                (
                    "Source provenance",
                    "Preserve source identities, revisions, "
                    "evidence state and limitations.",
                ),
                ("Appendix", "Provide authored technical appendices."),
            )
        ),
        required_section_variants=(("summary", "source-provenance"),),
        permitted_content=(*_CONTENT, "diagram"),
        callouts=_CALLOUTS,
        authored_sections=True,
    ),
    _profile(
        "project-brief",
        "Align an engagement's objectives, scope, and delivery expectations.",
        (
            _section(
                "Executive Summary", "Summarize the engagement and intended outcome."
            ),
            _section("Context", "Describe the business context and problem."),
            _section("Objectives", "State the outcomes the engagement should achieve."),
            _section("Scope", "Define included work and explicit exclusions."),
            _section("Approach", "Describe the proposed delivery approach."),
            _section("Deliverables", "List the expected deliverables."),
            _section("Success Criteria", "Define how success will be assessed."),
            _section("Risks", "Describe assumptions and delivery risks."),
            _section("Next Steps", "Identify actions, owners, and timing."),
            _section("Appendix", "Provide supporting material."),
        ),
        (
            (
                "executive-summary",
                "context",
                "objectives",
                "scope",
                "approach",
                "deliverables",
                "success-criteria",
            ),
        ),
    ),
    _profile(
        "analytics-report",
        "Explain what the data shows, what changed, and what it means.",
        (
            _section(
                "Executive Summary", "Summarize the principal analytical conclusions."
            ),
            _section(
                "Business Question or Objective",
                "State the analytical question.",
                "Objective",
            ),
            _section(
                "Data and Methodology",
                "Describe inputs, methods, and comparison periods.",
                "Methodology",
            ),
            _section(
                "Key Metrics",
                "Present metrics supplied by the consuming analysis.",
                "KPI Overview",
            ),
            _section("Findings", "Describe observed findings.", "Key Findings"),
            _section(
                "Charts and Tables", "Present supporting charts and publication tables."
            ),
            _section(
                "Interpretation",
                "Explain the implications of the results.",
                "Supporting Analysis",
            ),
            _section(
                "Recommendations or Implications",
                "State recommended action or implications.",
                "Recommendations",
            ),
            _section("Limitations", "Describe uncertainty and limitations."),
            _section("Appendix", "Provide detailed supporting analysis."),
        ),
        (
            (
                "executive-summary",
                "business-question-or-objective",
                "data-and-methodology",
                "findings",
                "interpretation",
                "recommendations-or-implications",
                "limitations",
            ),
            (
                "executive-summary",
                "key-metrics",
                "findings",
                "interpretation",
                "recommendations-or-implications",
            ),
        ),
    ),
    _profile(
        "assessment-report",
        "Evaluate current state, identify deficiencies, and recommend change.",
        (
            _section(
                "Executive Summary", "Summarize the assessment and proposed changes."
            ),
            _section("Current State", "Describe the state being assessed."),
            _section(
                "Assessment",
                "Evaluate strengths and deficiencies against explicit criteria.",
            ),
            _section("Findings", "Describe evidence-backed strengths and gaps."),
            _section(
                "Recommendations",
                "Prioritize changes and explain their expected benefit.",
            ),
            _section("Methodology", "Explain the assessment approach."),
            _section("Risks", "Describe implementation risks and assumptions."),
            _section("Limitations", "State limitations of the assessment."),
            _section("Appendix", "Provide supporting evidence."),
        ),
        (
            (
                "executive-summary",
                "current-state",
                "assessment",
                "findings",
                "recommendations",
            ),
        ),
    ),
    _profile(
        "decision-memo",
        "Explain a decision, its alternatives, rationale, and risks.",
        (
            _section("Executive Summary", "Summarize the decision and recommendation."),
            _section("Decision", "State the decision that must be made."),
            _section("Options", "Describe the viable alternatives."),
            _section("Recommendation", "Identify the recommended option."),
            _section("Rationale", "Explain the evidence and decision criteria."),
            _section("Risks", "Describe risks and tradeoffs."),
            _section("Next Steps", "Identify follow-up actions and ownership."),
            _section("Appendix", "Provide supporting material."),
        ),
        (
            (
                "executive-summary",
                "decision",
                "options",
                "recommendation",
                "rationale",
                "risks",
            ),
        ),
    ),
)


def list_profiles() -> tuple[DocumentProfile, ...]:
    for profile in _PROFILES:
        profile.validate_schema()
    return _PROFILES


def get_profile(doc_type: str) -> DocumentProfile:
    for profile in list_profiles():
        if profile.identity == doc_type:
            return profile
    raise ProfileValidationError(
        f"frontmatter.doc_type: unsupported profile {doc_type!r}"
    )


def scaffold_markdown(doc_type: str, doc_name: str) -> str:
    """Return an unfilled source; authors must fill sections before compiling."""
    profile = get_profile(doc_type)
    title = doc_name.replace("-", " ").title()
    profile.validate_instance(
        {"doc_type": doc_type, "doc_name": doc_name, "title": title},
        profile.required_section_variants[0],
    )
    headings = [
        section.title
        for section in profile.sections
        if section.identity in profile.required_section_variants[0]
    ]
    return (
        f"---\ndoc_type: {doc_type}\ndoc_name: {doc_name}\ntitle: {title}\n---\n\n"
        + "\n\n".join(f"## {heading}\n" for heading in headings)
        + "\n"
    )
