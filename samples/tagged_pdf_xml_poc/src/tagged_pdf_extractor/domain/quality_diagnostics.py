"""Central diagnostic classifications used by extraction quality gates."""

UNRESOLVED_REFERENCE_DIAGNOSTIC_CODES = (
    "unresolved_mcid",
    "unresolved_page_reference",
    "unsupported_objr",
    "tagged_xobject_unresolved",
)

# These codes mean source text or a referenced content object may not have
# reached the extracted document. Scope-balancing warnings are intentionally
# excluded because they do not, by themselves, prove text loss.
EXTRACTION_LOSS_DIAGNOSTIC_CODES = (
    *UNRESOLVED_REFERENCE_DIAGNOSTIC_CODES,
    "unsupported_stream_mcr",
    "tagged_form_xobject_unsupported",
    "tagged_xobject_unsupported",
    "invalid_mcid",
    "unsupported_structure_kid",
)
