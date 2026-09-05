# ZG RF and DoC Markdown Formatting Design

## Goal

Improve reviewer Markdown for the verified `ZG XN ZT_L05 + BOOK` layout without
hardcoding English or localized wording:

1. Preserve PDF-authored RF specification line breaks that occur after commas.
2. Render the strongest Declaration of Conformity title as a Markdown heading.
3. Render the repeated DoC section labels as bold text while leaving their child
   details as ordinary text.

This work does not implement OCR, manual-code comparison, icon recognition, or
checklist/report database behavior.

## Scope and Dispatch

The Markdown renderer remains buyer-independent. New evidence collection and
formatting primitives must also be reusable and must not contain title,
translation, language, or buyer wording dictionaries.

Activation is initially limited to the verified profile represented by the source
filename token `ZG XN ZT_L05` with `doc_type=BOOK`. All five language sections in
the BOOK PDF are eligible because matching uses structure and typography rather
than localized text. Other profiles retain their current output until their PDFs
validate the same behavior and their dispatch scope is explicitly enabled. XY ENG
and KR KOR are explicit negative-control profiles: their extraction must remain
unchanged and they must not receive ZG-only RF or DoC display hints.

The isolated POC must not import the root application's profile repository. A
small local profile-scope policy parses the source token from the standard PDF
filename and records the verified `ZG XN ZT_L05 -> BOOK` activation key. This is
layout dispatch metadata, not heading or translated-text matching. Unknown or
malformed filenames receive no profile-specific formatting.

Dispatch must be isolated from the Markdown writer. The writer consumes semantic
XML display evidence and does not parse source filenames or profile names.

## RF Line-Break Evidence

The ZG semantic XML already preserves PDF-authored line breaks as inline elements
whose `actual-text` is a newline. The current Markdown writer flattens these
elements to spaces.

A line break is eligible for reviewer Markdown only when all conditions hold:

- the target paragraph is inside a table cell;
- the source provides an explicit inline `actual-text="\n"` boundary;
- the visible source text immediately before that boundary ends with a comma;
- the boundary separates two non-empty visible text segments.

The implementation must never split text merely because it contains a comma.
Model names, RF labels, units, frequencies, languages, and literal RF wording must
not participate in detection.

For the current samples, this rule selects the 90 comma-following newline markers
in ZG RF table cells. It does not select ZC, the two non-comma ZA newline markers,
or the non-comma Italian Correct Disposal title/qualifier boundary.

The semantic XML must retain the source `actual-text` evidence. Markdown rendering
must preserve the text exactly and only change the separator from a space to a
line break.

## DoC Cluster Detection

DoC formatting is a two-stage decision. Individual bold-looking paragraphs must
not be promoted globally.

### Stage 1: Validate a Form-Like Typography Cluster

A candidate cluster must be a single structural section that contains:

- an initial short paragraph with the unique strongest typography tier;
- at least three later short paragraphs in a middle typography tier;
- ordinary-detail paragraphs in a weaker typography tier after those labels;
- at least one table whose cells repeat a strong short label followed by weaker
  detail paragraphs;
- a consistent relative order of `cluster title > labels > body` for both font
  weight and font size.

Comparison is relative within the section. The observed SamsungOne weights and
sizes (`800/8`, `600/7`, `400/6.5`) are test evidence, not runtime constants for
identifying DoC text.

The cluster must be rejected when typography is missing or ambiguous, the title
tier is not unique, fewer than three label/body groups exist, the table evidence
is absent, or the candidate overlaps an existing heading promotion.

### Stage 2: Assign Display Roles Inside a Validated Cluster

- The unique strongest initial paragraph receives a level-2 Markdown heading
  display hint.
- Middle-tier short paragraphs followed by weaker detail content receive a bold
  label display hint.
- A strong first paragraph inside a table cell followed by weaker paragraphs in
  that cell receives the same bold label hint.
- Ordinary details, signatures, notes, bullets, and figures retain their existing
  semantic roles and text.
- A label that cannot be tied to weaker following detail remains plain text.

The raw XML remains unchanged. Semantic XML records explicit evidence attributes
for the heading and bold-label hints so the Markdown writer does not repeat the
detection logic.

## Expected Markdown Shape

```markdown
## Declaration of Conformity

**Manufacturer**

Name: Samsung

**Product Details**

Product: Smart Control

**Declaration and applicable standards**

We hereby declare ...

**EMC**

EN 301 489-1 V2.2.3

**Safety**

EN IEC 62368-1:2020+A11:2020

**Radio**

EN 300 328 V2.2.2
```

The example illustrates rendering only. None of its wording may appear in runtime
detection code.

## Architecture and Data Flow

1. The tagged PDF reader produces the existing structure and text-style evidence.
2. Profile dispatch determines whether the ZG BOOK formatting analyzers are
   enabled.
3. A reusable RF boundary analyzer records eligible source-authored line-break
   paths.
4. A reusable form-cluster analyzer records one heading hint and zero or more
   bold-label hints after validating the complete section.
5. Semantic XML serializes those hints without changing source text or raw XML.
6. The Markdown writer renders only the serialized evidence.
7. Output validation rejects unresolved, duplicate, overlapping, or structurally
   invalid hint paths before publication.

The extraction entry point remains orchestration only. New behavior belongs in
dedicated domain modules and profile dispatch, not in the Markdown writer or a
language-specific string rule.

## Failure and Safety Behavior

- Missing profile metadata or unmatched profile: keep current Markdown output.
- Missing/ambiguous font evidence: do not format the candidate.
- Invalid or overlapping display hints: fail validation before atomic publication.
- Unresolvable RF newline evidence: preserve current joined text rather than
  inventing a split.
- Existing numbered chapter headings and Correct Disposal subtitle hints take
  precedence and must not be duplicated or overridden.

## Verification

Unit tests must prove:

- an explicit comma-following newline inside a table cell is preserved;
- an ordinary comma without source newline evidence is not split;
- non-comma `actual-text` newlines retain existing behavior;
- RF evidence outside the enabled profile is not activated;
- a complete three-tier form cluster produces one level-2 heading and bold labels;
- incomplete clusters, missing table evidence, ambiguous typography, and existing
  heading candidates remain unchanged;
- table-cell labels and their child details remain separate and in source order;
- raw XML contains no Markdown display metadata;
- invalid/duplicate/overlapping hints prevent publication atomically.

Real-sample regression tests must cover ZG ENG, DEU, FRA, ITA, and DUT DoC sections,
both English DoC instances, all verified RF rows, unchanged ZC/ZA output, unchanged
numbered chapter headings, and unchanged Correct Disposal formatting. XY ENG and
KR KOR must also be extracted as required samples and must prove that no ZG-only
RF line-break, DoC heading, or DoC bold-label hints are emitted.

The final gate is the complete POC test suite with required ZC, ZA, ZG, XY, and KR
samples, POC/repository compile checks, no-title-hardcoding audit, regenerated ZG
reviewer Markdown, and unchanged reviewer Markdown bundles for XY and KR.
