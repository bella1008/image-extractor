from __future__ import annotations

from src.models import PdfProfile, PdfStructure, StructureValidationResult, ValidationIssue


def validate_structure(profile: PdfProfile, structure: PdfStructure) -> StructureValidationResult:
    issues: list[ValidationIssue] = []

    if profile.doc_type != structure.detected_doc_type:
        issues.append(
            ValidationIssue(
                field="doc_type",
                expected=profile.doc_type,
                actual=structure.detected_doc_type,
                severity="review_required",
                message="Profile doc_type does not match the actual PDF structure.",
            )
        )

    actual_languages = detected_languages(structure)
    if not actual_languages and profile.language_count == 1:
        actual_languages = profile.languages
    if profile.language_count != len(actual_languages):
        issues.append(
            ValidationIssue(
                field="language_count",
                expected=str(profile.language_count),
                actual=str(len(actual_languages)),
                severity="review_required",
                message="Profile language_count does not match detected language pages.",
            )
        )

    if profile.languages != actual_languages:
        issues.append(
            ValidationIssue(
                field="languages",
                expected=";".join(profile.languages),
                actual=";".join(actual_languages),
                severity="review_required",
                message="Profile language order/list does not match detected PDF language labels.",
            )
        )

    status = "PASS" if not issues else "REVIEW_REQUIRED"
    return StructureValidationResult(status=status, issues=tuple(issues))


def detected_languages(structure: PdfStructure) -> tuple[str, ...]:
    if structure.language_sections:
        return tuple(section.language for section in structure.language_sections)

    languages: list[str] = []
    for page in structure.language_pages:
        if page.language.startswith("PAGE-"):
            continue
        if page.language not in languages:
            languages.append(page.language)
    return tuple(languages)
