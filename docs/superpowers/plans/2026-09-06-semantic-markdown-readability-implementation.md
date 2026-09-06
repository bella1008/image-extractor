# Semantic Markdown Readability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PDF 태그 계층과 원문을 바꾸지 않으면서, 한 목록·표 셀 안의 문장 줄바꿈, 문장 내 소형 아이콘의 `[아이콘]` 표시, 의미 있는 `※` 라벨과 간격을 사람이 검토하기 좋은 Markdown으로 보존한다.

**Architecture:** 기존 ZG 전용 RF/DoC 규칙 뒤에 구매처·언어 비종속 `apply_readability_formatting()` 단계를 둔다. 도메인 탐지기는 보수적인 문장 경계와 인라인 아이콘을 불변 힌트로 만들고, 중앙 검증기가 구조 경로·원문 재탐지·기하 근거·기존 표시 규칙과의 충돌을 검증한다. Semantic XML만 검증된 표시 근거를 기록하며, Markdown 작성기는 XML 근거와 원래 `※` 라벨만 렌더링한다. Raw XML과 PDF 관찰 구조는 변경하지 않는다.

**Tech Stack:** Python 3.11+, frozen dataclasses, `pypdf`, PyMuPDF, `xml.etree.ElementTree`, pytest. 새 NLP/OCR 의존성은 추가하지 않는다.

---

## File Map

- Create `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/readability_formatting.py`: 공용 문장 경계 탐지, 인라인 아이콘 탐지, 기하·텍스트 흐름 분석과 가독성 힌트 적용.
- Modify `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`: `SentenceBreakHint`, `InlineIconHint`와 `TaggedDocument` 기본 빈 튜플 필드 추가.
- Modify `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/display_hint_validation.py`: 신규 힌트 경로, 오프셋, 재탐지 근거와 충돌을 중앙 검증.
- Modify `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/extract_document.py`: ZG 전용 표시 규칙 뒤, 출력 검증 전에 공용 가독성 단계 연결.
- Modify `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py`: Semantic XML의 `<text>`와 `<figure>`에만 신규 표시 근거 직렬화.
- Modify `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`: 문장 경계, 인라인 아이콘, `※` 라벨·간격 렌더링.
- Modify `samples/tagged_pdf_xml_poc/tests/test_display_hint_validation.py`: 신규 힌트의 정상·위조·충돌 검증.
- Modify `samples/tagged_pdf_xml_poc/tests/test_xml_writer.py`: Semantic/Raw XML 분리와 힌트 소비 검증.
- Modify `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`: 한 구조 안의 시각적 줄바꿈, 아이콘 순서, `※` 표시 검증.
- Modify `samples/tagged_pdf_xml_poc/tests/test_output_bundle.py`: 파이프라인 순서와 실패 시 기존 묶음 보존 검증.
- Modify `samples/tagged_pdf_xml_poc/tests/test_layout_regression.py`: ZG 양성 사례와 ZC/KR 실물 PDF 회귀 게이트를 분리하고 기존 ZA/XY 단위 테스트는 보존.
- Modify `samples/tagged_pdf_xml_poc/README.md`: 신규 표시 의미, 보수적 판별 범위와 검토 방법 문서화.

### Task 1: Immutable Readability Hint Models

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_readability_formatting.py`

- [ ] **Step 1: Write failing compatibility and immutability tests**

기존 위치 인자 생성자가 깨지지 않도록 신규 필드는 `TaggedDocument` 끝에 기본 빈 튜플로 추가한다. 경로와 오프셋은 exact integer만 허용하도록 이후 중앙 검증에서 다루고, 모델 자체는 불변 데이터만 표현한다.

```python
def test_readability_hints_are_frozen_and_document_defaults_are_empty() -> None:
    sentence = SentenceBreakHint(
        child_path=(0, 1, 2),
        offsets=(41, 97),
    )
    icon = InlineIconHint(
        child_path=(0, 1, 3),
        page_index=4,
        bbox=(10.0, 20.0, 19.0, 29.0),
        reference_font_size=6.5,
        width_ratio=9.0 / 6.5,
        height_ratio=9.0 / 6.5,
    )
    assert sentence.offsets == (41, 97)
    assert icon.page_index == 4
    with pytest.raises(FrozenInstanceError):
        sentence.offsets = ()  # type: ignore[misc]
    document = TaggedDocument(Path("manual.pdf"), True, None, (), ())
    assert document.sentence_break_hints == ()
    assert document.inline_icon_hints == ()
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
Set-Location samples\tagged_pdf_xml_poc
.\.venv\Scripts\python -m pytest tests\test_readability_formatting.py -q
```

Expected: import failure for the missing hint classes.

- [ ] **Step 3: Add the minimal frozen dataclasses**

```python
@dataclass(frozen=True)
class SentenceBreakHint:
    child_path: tuple[int, ...]
    offsets: tuple[int, ...]
    reason: str = "conservative_sentence_terminal_in_review_container"


@dataclass(frozen=True)
class InlineIconHint:
    child_path: tuple[int, ...]
    page_index: int
    bbox: tuple[float, float, float, float]
    reference_font_size: float
    width_ratio: float
    height_ratio: float
    reason: str = "small_inline_figure_with_adjacent_text"
```

`TaggedDocument` 끝에 다음 필드를 추가한다.

```python
sentence_break_hints: tuple[SentenceBreakHint, ...] = ()
inline_icon_hints: tuple[InlineIconHint, ...] = ()
```

- [ ] **Step 4: Run the focused test and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests\test_readability_formatting.py tests\test_review_formatting.py -q
.\.venv\Scripts\python -m compileall src tests
```

Expected: model tests and existing ZG formatting tests pass.

Commit: `Add semantic readability hint models`

### Task 2: Conservative Sentence-Break Detection

**Files:**
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/readability_formatting.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_readability_formatting.py`

- [ ] **Step 1: Write RED tests for eligible structure and retained hierarchy**

합성 구조로 다음 두 양성 사례를 만든다.

```text
list > list_item > list_body > paragraph > text fragments
table > table_row > table_cell > paragraph > text fragments
```

첫 사례는 프랑스어 네 문장, 둘째는 독일어 세 문장을 사용한다. 문장 시작이 같은 `ContentFragment` 안에 있는 경우와 다음 fragment에서 시작하는 경우를 모두 포함한다. 탐지 결과는 문장이 시작되는 직렬화 `<text>`의 `child_path`와 해당 문자열 안의 삽입 `offset`으로 표현한다. 여러 경계가 같은 fragment에 있으면 하나의 힌트의 정렬된 `offsets`에 합친다.

```python
def test_detects_sentence_starts_without_splitting_list_or_table_structure() -> None:
    document = _document(
        _list_body("Première phrase. Deuxième phrase. Troisième phrase. Quatrième phrase."),
        _table_cell("Erster Satz. Zweiter Satz. Dritter Satz."),
    )
    hints = detect_sentence_break_hints(document)
    assert sum(len(hint.offsets) for hint in hints) == 5
    assert all(_resolve(document, hint.child_path).__class__ is ContentFragment for hint in hints)
```

- [ ] **Step 2: Write RED tests for conservative exclusions**

각 보호 패턴과 모호한 경계를 독립적으로 검증한다.

- URL: `https://www.samsung.com/support.`
- 이메일: `service.eu@example.com.`
- 소수: `2.5 GHz`, `0.3 W`.
- 버전·표준: `V2.2.3`, `EN 301 489-1 V2.2.3`.
- 압축 약어·이니셜: `e.g.`, `i.e.`, `A. B. Smith`.
- 말줄임표: `Wait… then continue.`
- 모델·파일형 토큰: `QE65LS03DAUXXN`, `manual.v2.xml`의 내부 마침표. `Open manual.v2.xml. Next`의 마지막 마침표는 정상 문장 경계로 남긴다.
- 대소문자가 없는 문자 체계: `문장입니다. 다음 문장입니다.`는 언어명 하드코딩 없이 Unicode `Lo` 문자 범주로 다음 문장 시작을 확인한다.
- 종결 부호 뒤 문자가 소문자이거나 문장 시작인지 확실하지 않은 경우.
- 일반 `paragraph` 본문, heading, caption, label, figure, 중첩 list/table처럼 승인 범위를 벗어난 구조.

또한 기존 `LineBreakHint`가 있는 구조 경계는 source break marker로 흐름을 분할해 같은 위치에 sentence break를 만들지 않는 테스트를 추가한다.

- [ ] **Step 3: Run sentence tests and verify RED**

Run: `.\.venv\Scripts\python -m pytest tests\test_readability_formatting.py -q`

Expected: missing module/detector failures.

- [ ] **Step 4: Implement a path-aware text-flow builder**

`readability_formatting.py`에 구조 child index를 그대로 쓰는 순회를 구현한다. 승인 컨테이너는 다음으로 제한한다.

- `list_body` 아래의 leaf `paragraph`, 또는 paragraph 없이 직접 이어진 inline text flow;
- `table_cell` 아래의 leaf `paragraph`.

heading·caption·label·figure·중첩 list/table을 통과해 텍스트를 합치지 않는다. 각 `ContentFragment`는 `join_text_parts(fragment.text_parts)`로 Semantic XML과 동일한 텍스트를 만들고, 전체 흐름의 각 보이는 문자를 `(child_path, local_offset)`에 매핑한다. fragment 사이에서 삽입된 공백은 다음 보이는 문자의 위치로 경계를 귀속한다.

- [ ] **Step 5: Implement protected-range sentence scanning**

외부 언어 모델이나 언어별 문장 사전을 사용하지 않는다. 먼저 URL·이메일·숫자 소수·점 연결 버전/파일 토큰·반복 점 약어·이니셜·말줄임표의 문자 범위를 보호한다. 그 밖의 `.`, `!`, `?` 뒤에서만 후보를 만들고, 닫는 따옴표·괄호와 공백을 건너뛴 다음 문자가 Unicode 대문자, 숫자, 또는 대소문자가 없는 문자 체계의 `unicodedata.category(character) == "Lo"`일 때만 승인한다. 여는 인용부호가 있으면 그 뒤 문자에 같은 판정을 적용한다. 모호하면 분리하지 않는다.

기존 `display-role="preserved-line-break"` 대상은 탐지 입력에서 경계 marker로 취급한다. marker 양쪽을 별도 segment로 검사해 기존 RF 줄바꿈과 같은 위치에 신규 경계를 만들지 않는다.

```python
def apply_readability_formatting(document: TaggedDocument) -> TaggedDocument:
    return replace(
        document,
        sentence_break_hints=detect_sentence_break_hints(document),
        inline_icon_hints=detect_inline_icon_hints(document),
    )
```

`detect_inline_icon_hints()`는 다음 Task가 구현하기 전까지 빈 튜플을 반환하는 실제 함수로 둔다.

- [ ] **Step 6: Run focused tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests\test_readability_formatting.py tests\test_text_joining.py tests\test_review_formatting.py -q
.\.venv\Scripts\python -m compileall src tests
```

Expected: 양성 경계 수가 정확하고 모든 보호·범위 제외 사례가 통과한다.

Commit: `Detect conservative sentence display breaks`

### Task 3: Geometry-Backed Inline Icon Detection

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/readability_formatting.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_readability_formatting.py`

- [ ] **Step 1: Write RED tests for one small inline figure**

paragraph 또는 list body의 동일 흐름 안에 `text -> figure -> text`와 `figure -> text` 사례를 만든다. figure에는 page와 `/BBox`, 주변 `ContentFragment`에는 같은 page와 `TextStyle(font_size=6.5)`를 준다. `9 x 9` figure는 각각 약 `1.384615`인 width/font와 height/font 비율 근거와 함께 한 번만 탐지되어야 한다.

```python
def test_small_figure_with_same_page_adjacent_text_is_inline_icon() -> None:
    document = _document(_paragraph_with_icon(width=9.0, height=9.0, font_size=6.5))
    hints = detect_inline_icon_hints(document)
    assert len(hints) == 1
    assert hints[0].child_path == (0, 1)
    assert hints[0].page_index == 3
    assert hints[0].bbox == (100.0, 200.0, 109.0, 209.0)
    assert hints[0].reference_font_size == 6.5
    assert hints[0].width_ratio == pytest.approx(9.0 / 6.5)
    assert hints[0].height_ratio == pytest.approx(9.0 / 6.5)
```

- [ ] **Step 2: Write RED rejection tests for every safety condition**

다음은 모두 힌트를 만들지 않아야 한다.

- figure가 문장 흐름의 유일한 내용인 경우;
- 앞뒤 같은 흐름에 보이는 텍스트가 없는 경우;
- figure가 paragraph/list-body text flow 밖의 독립 block인 경우. 실제 ZG 문장 내 9×9 figure도 source attribute가 `/Placement=/Block`이므로 이 속성만으로는 거부하지 않는다;
- page index 또는 `/BBox`가 없거나 BBox가 유한하지 않은 경우;
- 폭·높이가 0 이하인 경우;
- 주변 글자 크기가 없거나 0/비유한인 경우;
- figure와 주변 text의 page가 다른 경우;
- `width / font_size > 3.0` 또는 `height / font_size > 2.0`인 경우;
- figure 안에 보이는 대체/추출 텍스트가 있어 일반 figure 텍스트로 렌더링해야 하는 경우;
- table cell의 독립 figure, heading, caption, label, 중첩 block에 있는 경우.

한쪽 텍스트만 있는 선두/후미 아이콘은 동일 leaf text flow에 다른 보이는 텍스트가 있고 기하 조건이 맞을 때 허용한다. 인접 text style이 여러 개면 보이는 문자 수 가중 중앙값을 기준 글자 크기로 사용한다.

- [ ] **Step 3: Run icon tests and verify RED**

Run: `.\.venv\Scripts\python -m pytest tests\test_readability_formatting.py -q`

Expected: icon tests fail because the detector still returns an empty tuple.

- [ ] **Step 4: Implement strict BBox and relative-size classification**

`/BBox`와 `BBox` 이름을 대소문자 구분 없이 받아 정확히 네 개의 유한 실수로 파싱한다. `/Placement`는 감사 근거로 보존하지만 판별 조건으로 사용하지 않는다. 실제 ZG의 문장 내 9×9 아이콘도 `/Placement=/Block`이므로, source attribute보다 figure의 실제 부모 text flow, 앞뒤 text 순서, page, BBox, 상대 크기를 우선한다. 이름, buyer, language, alt text 번역, OCR, 이미지 유사도를 사용하지 않는다.

고정 공용 임계값은 다음과 같다.

```python
_MAX_INLINE_ICON_WIDTH_FONT_RATIO = 3.0
_MAX_INLINE_ICON_HEIGHT_FONT_RATIO = 2.0
```

figure path, page, BBox, 상대 비율을 `InlineIconHint`에 남긴다. 원본 figure의 object-ref와 source attributes는 기존 Semantic XML 요소가 이미 보존하므로 복제하지 않는다.

- [ ] **Step 5: Run focused tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests\test_readability_formatting.py tests\test_typography.py -q
.\.venv\Scripts\python -m compileall src tests
```

Expected: 아이콘 양성·음성 사례와 기존 typography 테스트가 통과한다.

Commit: `Classify geometry-backed inline icons`

### Task 4: Central Validation and Pipeline Wiring

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/display_hint_validation.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/extract_document.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_display_hint_validation.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_output_bundle.py`

- [ ] **Step 1: Write RED validation tests for sentence hints**

다음을 검증한다.

- target이 실제 `ContentFragment`이고 offsets가 정렬된 중복 없는 exact integer일 때 승인;
- 빈 path, 음수/bool/non-tuple path, 미해결 path, `StructureElement` target 거부;
- 빈 offsets, `0`보다 작거나 직렬화 텍스트 길이 이상인 offset, bool, 중복, 역순 거부;
- offset이 공백·문장 중간·보호 토큰 안에 있거나 detector 재계산 결과와 다르면 거부;
- source RF break, heading promotion, subtitle, section heading/strong label 하위와 충돌하면 거부.

`offset=0`은 fragment 경계에서 다음 문장이 시작되는 정상 표현이므로 허용하고, 마지막 문자 뒤인 `offset=len(text)`는 거부한다.

- [ ] **Step 2: Write RED validation tests for icon hints**

다음을 검증한다.

- target이 `figure`이고 자동 detector가 산출한 page/BBox/font size/ratio/reason과 정확히 일치할 때 승인;
- duplicate/unresolved/non-figure path, 잘못된 tuple 길이, bool/NaN/inf/0 이하 수치 거부;
- page/BBox/ratio를 수동 변조하거나 구조상 인라인이 아닌 figure를 힌트로 위조하면 거부;
- heading promotion, subtitle, text-display hint target과 상하위 path가 겹치면 거부.

- [ ] **Step 3: Extend immutable validation result and implement exact re-detection**

```python
@dataclass(frozen=True)
class ValidatedReviewFormattingHints:
    line_break_by_path: Mapping[tuple[int, ...], LineBreakHint]
    text_display_by_path: Mapping[tuple[int, ...], TextDisplayHint]
    sentence_break_by_path: Mapping[tuple[int, ...], SentenceBreakHint]
    inline_icon_by_path: Mapping[tuple[int, ...], InlineIconHint]
```

모든 mapping은 `MappingProxyType`으로 반환한다. 신규 힌트는 같은 문서를 다시 탐지한 결과와 dataclass 값 전체가 일치해야 한다. 자동 탐지와 수동 공급 데이터가 동일한 검증 규칙을 거치게 한다.

- [ ] **Step 4: Write and implement pipeline-order RED test**

`ExtractDocument.run()`의 순서를 spy/monkeypatch로 다음과 같이 고정한다.

```text
reader
numbered heading promotion
subtitle detection
ZG profile review formatting
generic readability formatting
baseline
writer validation
quality evaluation
atomic write
```

그 뒤 `extract_document.py`에서 `apply_profile_review_formatting(document)` 바로 다음에 `apply_readability_formatting(document)`를 호출한다. 구매처 dispatch를 추가하지 않는다.

- [ ] **Step 5: Prove validation failure publishes nothing**

위조 sentence/icon hint를 가진 문서로 `OutputBundleWriter.validate()`가 실패하고, 기존 네 산출물의 byte가 그대로 남는 테스트를 추가한다. 이는 기존 staging/rollback 계약을 재사용한다.

- [ ] **Step 6: Run focused tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests\test_display_hint_validation.py tests\test_output_bundle.py tests\test_review_formatting.py -q
.\.venv\Scripts\python -m compileall src tests
```

Expected: 신규 원자적 검증과 기존 ZG 규칙이 모두 통과한다.

Commit: `Validate and wire generic readability hints`

### Task 5: Semantic XML Evidence Without Raw XML Mutation

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_xml_writer.py`

- [ ] **Step 1: Write Semantic XML RED assertions**

문장 경계 target인 `<text>`는 다음처럼 직렬화한다.

```xml
<text page-index="18" mcid="27"
      display-role="sentence-break-source"
      sentence-break-offsets="0,17"
      sentence-break-reason="conservative_sentence_terminal_in_review_container">Deuxième phrase. Troisième phrase.</text>
```

인라인 figure는 기존 page/object-ref/BBox source evidence와 함께 다음 표시 속성을 갖는다.

```xml
<figure page-index="0" object-ref="123 0 R"
        display-role="inline-icon"
        icon-reason="small_inline_figure_with_adjacent_text"
        reference-font-size="6.5"
        width-font-ratio="1.384615"
        height-font-ratio="1.384615"><text /></figure>
```

문장 offsets는 comma-separated ASCII integer로 고정하고 XML writer의 `_format_number()`를 비율에도 재사용한다.

- [ ] **Step 2: Write Raw XML and complete-consumption RED assertions**

같은 `TaggedDocument`를 `write_raw()`로 쓴 결과에는 `display-role`, `sentence-break-*`, `icon-reason`, `reference-font-size`, `*-font-ratio`가 한 건도 없어야 한다. 원래 fragment parts, figure attributes, page, MCID, object-ref는 기존 canonical signature와 동일해야 한다.

신규 힌트 path가 직렬화 중 소비되지 않으면 다른 표시 힌트와 똑같이 `unresolved sentence break hint path` 또는 `unresolved inline icon hint path`로 실패해야 한다.

- [ ] **Step 3: Implement semantic-only serialization**

`write_semantic()`에 검증된 두 mapping과 consumed path set을 추가하고 `_append_semantic_child()`까지 전달한다. `ContentFragment` 분기에서 sentence 속성을 `<text>`에 추가하고, `StructureElement` 분기에서 icon 속성을 해당 `<figure>`에 추가한다. 기존 `expected_parts`, join decisions, raw writer 코드는 바꾸지 않는다.

- [ ] **Step 4: Run focused tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests\test_xml_writer.py tests\test_display_hint_validation.py tests\test_output_bundle.py -q
.\.venv\Scripts\python -m compileall src tests
```

Expected: Semantic XML만 표시 근거를 가지며 왕복 텍스트·원자적 출력 검증이 통과한다.

Commit: `Serialize semantic readability evidence`

### Task 6: Markdown Sentence and Inline-Icon Rendering

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`

- [ ] **Step 1: Write RED tests for sentence boundaries in one list item**

Semantic XML의 한 `list_item > list_body > paragraph` 안 네 문장 중 세 target offset에 표시 근거를 둔다. 출력은 bullet 하나만 가지며 continuation은 같은 bullet indentation으로 렌더링되어야 한다.

```markdown
- Veillez à brancher correctement et complètement le cordon d'alimentation.<br>
  Lorsque vous débranchez le cordon d'alimentation d'une prise murale, tirez toujours sur la fiche du cordon d'alimentation.<br>
  Ne le débranchez jamais en tirant sur le cordon d'alimentation.<br>
  Ne touchez pas le cordon d'alimentation si vous avez les mains mouillées.
```

`markdown.count("- Veillez") == 1`이고 후속 문장에는 `-`가 없어야 한다. Semantic XML의 list/list_item/list_body/paragraph 개수는 렌더링 전후 의미 비교에서 그대로여야 한다.

- [ ] **Step 2: Write RED tests for table-cell rendering and protected Markdown**

복잡한 표 셀은 기존 `- 행 N / - 열 N` 구조 아래 한 paragraph의 문장들을 `<br>`와 동일 cell indentation으로 표시한다. safe pipe table 안에 신규 문장 경계가 있으면 물리 newline으로 pipe 행을 깨지 않고 `<br>`만 셀 내부에 사용한다. 일반 pipe escaping `\|`, headings, list indentation, source RF physical lines는 그대로 유지한다.

Malformed 또는 수동 삽입한 `sentence-break-*` 속성은 Markdown이 추론·수선하지 않는다. XML writer validation을 거치지 않은 잘못된 offset은 `ValueError`로 명시적으로 거부한다.

- [ ] **Step 3: Write RED tests for icon order and fallback**

```xml
<paragraph>
  <text>menu (</text>
  <figure display-role="inline-icon" page-index="0" icon-reason="small_inline_figure_with_adjacent_text" reference-font-size="6.5" width-font-ratio="1.4" height-font-ratio="1.4"><text /></figure>
  <text>&gt; left directional button &gt;</text>
  <figure display-role="inline-icon" page-index="0" icon-reason="small_inline_figure_with_adjacent_text" reference-font-size="6.5" width-font-ratio="1.4" height-font-ratio="1.4"><text /></figure>
  <text>Settings)</text>
</paragraph>
```

Expected single flow:

```text
menu ( [아이콘] > left directional button > [아이콘] Settings)
```

아이콘은 원래 child 순서에 나타나고, 이름을 붙이지 않는다. 표시 근거가 없는 empty figure, standalone/large/uncertain figure는 기존 `[그림: 텍스트 없음]` block으로 남는다. text가 있는 figure는 기존 figure text를 유지한다.

- [ ] **Step 4: Implement explicit display sentinels**

기존 `_PRESERVED_LINE_BREAK`와 별도로 `_SENTENCE_BREAK` sentinel을 둔다. `<text sentence-break-offsets="0,17">` 같은 근거를 읽을 때 visible text의 정확한 위치에 sentinel을 삽입한다. `_join_text_parts()`는 sentence sentinel을 유지하고 일반 block/list 출력에서 `<br>\n`으로, safe pipe cell에서는 `<br>`로 변환한다. source RF break는 계속 물리 newline이며 신규 sentence break와 합치지 않는다.

`figure[display-role="inline-icon"]`은 `_mixed_content_events()`와 `_list_events()`에서 block이 아니라 text token `[아이콘]`으로 처리한다. 표시 근거 없는 figure의 기존 지연/fallback 로직은 유지한다.

- [ ] **Step 5: Prove render/write identity and no duplication**

`MarkdownDocumentWriter.render_text()` 반환 byte와 `write()` 파일 byte가 동일한지, 문장과 아이콘 텍스트가 각각 한 번만 등장하는지, candidate heading이나 numbered heading 아래에서 중복되지 않는지 테스트한다.

- [ ] **Step 6: Run focused tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests\test_markdown_writer.py tests\test_xml_writer.py tests\test_output_bundle.py -q
.\.venv\Scripts\python -m compileall src tests
```

Expected: 목록·표 구조가 유지된 채 시각적 문장 줄바꿈과 `[아이콘]`이 정확한 위치에 나타난다.

Commit: `Render sentence breaks and inline icons`

### Task 7: Preserve `※` as a Semantic Note Marker

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`

- [ ] **Step 1: Write RED tests for a direct `※` list label**

```xml
<list>
  <list_item>
    <label><text>※</text></label>
    <list_body><paragraph><text>Cette adresse n'est pas celle du Centre de service Samsung.</text></paragraph></list_body>
  </list_item>
</list>
```

Expected exactly:

```text
※ Cette adresse n'est pas celle du Centre de service Samsung.
```

`- ※`, 단독 `-`, label 누락, 본문 중복이 없어야 한다. `※`와 body는 원래 하나의 `list_item`에 남는다.

- [ ] **Step 2: Write RED tests for inline spacing and safe fallback**

분리된 text/span fragment가 `UK`, whitespace, `※`, whitespace, `2025-10-31`을 제공할 때 `UK ※ 2025-10-31`로 표시한다. 이미 올바른 공백은 한 칸으로 정규화하고, 줄 시작 `※` 앞에는 불필요한 공백을 만들지 않는다.

기존 테스트를 확장해 `Ł`, `Œ`, `•`, `–`, 임의 문자열 label은 note marker가 아니며 현재의 안전한 `-` 구조 fallback을 유지함을 검증한다. 순서형 `1.`, `A.`, `(1)` 처리도 바뀌지 않아야 한다.

- [ ] **Step 3: Implement separate label classes**

```python
_SEMANTIC_NOTE_MARKERS = frozenset({"※"})
```

`_analyze_list_labels()`의 반환을 ordered marker, note marker, retained content labels가 구분되는 작은 불변 결과로 바꾼다. note marker가 direct label 하나일 때 `_render_list_item()`은 Markdown bullet을 만들지 않고 `※ body`를 첫 줄로 쓴다. 다른 label과 혼합되어 모호하면 기존 `-` fallback을 선택한다.

`_join_text_parts()`의 최종 display normalization에서 inline `※` 양쪽의 사라진 whitespace fragment만 복구한다. 원문 XML, 모델 코드, 일반 구두점에는 손대지 않는다.

- [ ] **Step 4: Run focused tests and commit**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests\test_markdown_writer.py tests\test_text_joining.py -q
.\.venv\Scripts\python -m compileall src tests
```

Expected: `※`는 의미 있는 note marker로 한 번만 보이고 손상 glyph와 일반 bullet 정책은 그대로다.

Commit: `Preserve semantic note markers in Markdown`

### Task 8: Three-Sample PDF Regression Gates

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/tests/test_layout_regression.py`
- Modify: `samples/tagged_pdf_xml_poc/README.md`

- [ ] **Step 1: Separate the existing XY/KR parameterized real-PDF test**

기존 XY/KR parameterized test를 같은 helper를 공유하는 `test_xy_retains_structure_without_zg_display_rules`와 `test_kr_retains_structure_without_zg_display_rules`로 나눈다. 이번 실물 PDF 검수에서는 KR만 선택 실행할 수 있게 하되 XY 테스트 코드와 기존 기대값은 삭제하지 않는다. `_assert_no_zg_display_evidence()`는 이름을 `_assert_no_zg_profile_display_evidence()`로 바꾸고 ZG 전용 `preserved-line-break`, `section-heading`, `strong-label`의 부재만 확인한다. 공용 `sentence-break-source`와 `inline-icon`은 구조 근거가 있을 때 ZC/KR에도 나타날 수 있으므로 전부 0이라고 단정하지 않는다.

- [ ] **Step 2: Add exact ZG positive assertions**

실제 ZG bundle에서 다음을 path/semantic text로 찾아 line number에 의존하지 않고 검증한다.

- FRA `Veillez à brancher correctement`로 시작하는 list item은 하나이며 네 visual sentence lines를 가짐;
- DEU battery-disposal table cell은 하나이며 세 visual sentence lines를 가짐;
- 검토된 OSD 문장 내 small figures는 Semantic XML에서 `inline-icon`이고 Markdown 원래 위치에서 `[아이콘]`으로 보임;
- FRA `※` direct label 설명은 `※ Cette adresse`로 시작하며 한 번만 보임;
- `UK ※ 2025-10-31` 간격이 보존됨;
- ZG 기존 `90` RF source breaks, `10` DoC section headings, `70` strong labels, 번호형 제목 `25`개와 subtitle 집계가 유지됨;
- bracketed model labels는 plain source text 그대로이며 추출기가 색상/escape 표시를 추가하지 않음.

- [ ] **Step 3: Add ZC/KR negative and structural controls**

ZC와 KR sample에 대해 다음을 검증한다. 기존 ZA/XY 단위·회귀 테스트 코드는 유지하지만 이번 변경의 필수 실물 PDF 실행 대상에서는 제외한다.

- raw XML에는 신규 display attributes가 없음;
- sentence break가 새 list item, paragraph, table row/cell을 만들지 않음;
- inline-icon은 detector 기하 근거와 1:1이고 unknown figure를 승격하지 않음;
- `[그림: 텍스트 없음]` fallback과 OSD 특수문자 `>`, `/`, `[`, `]`, `(`, `)`가 유지됨;
- 기존 번호형 heading 수와 text, ZG 전용 규칙 부재, report `status=pass`가 유지됨.

- [ ] **Step 4: Run required three-sample PDF regression suite**

Run from `samples/tagged_pdf_xml_poc` after resolving all paths from the repository sample tree:

```powershell
$env:TAGGED_PDF_REQUIRE_SAMPLES = "1"
$env:TAGGED_PDF_ZC_SAMPLE = (Resolve-Path "..\SUG_RAW\0_TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf").Path
$env:TAGGED_PDF_ZG_SAMPLE = (Resolve-Path "..\SUG_RAW\1_TV_ZG\BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf").Path
$env:TAGGED_PDF_KR_SAMPLE = (Resolve-Path "..\SUG_RAW\TV_KR\BN68-25108A-00_SUG_Y26 TV ALL_KR_KOR_251218.0.pdf").Path
.\.venv\Scripts\python -m pytest `
  tests\test_zc_integration.py::test_zc_pdf_has_recoverable_tagged_hierarchy_and_auditable_outputs `
  tests\test_layout_regression.py::test_zg_retains_all_pages_without_false_image_xobject_loss `
  tests\test_layout_regression.py::test_kr_retains_structure_without_zg_display_rules `
  -q
```

Expected: ZC, ZG, KR 필수 sample이 skip 없이 실행되고 모든 구조·가독성 assertion이 통과한다. ZA/XY PDF는 이 명령에서 열지 않는다.

- [ ] **Step 5: Document the review contract and commit**

README에 다음을 기록한다.

- `<br>`는 같은 source list item/table cell 안의 표시용 문장 경계이지 구조 분리가 아님;
- `[아이콘]`은 이름을 식별한 결과가 아니라 주변 문장·page·BBox·상대 크기로 확인된 small inline figure임;
- `[그림: 텍스트 없음]`은 standalone/large/uncertain fallback임;
- `※`는 PDF의 의미 있는 source label이며 `Ł`, `Œ`와 구분됨;
- bracket label의 editor 색상 차이는 source style이 아님.

Run:

```powershell
.\.venv\Scripts\python -m pytest tests\test_layout_regression.py tests\test_markdown_writer.py -q
.\.venv\Scripts\python -m compileall src tests
```

Commit: `Gate readability changes across three PDF profiles`

### Task 9: Regenerate Human-Review Bundles and Final Verification

**Files:**
- Generate locally under: `samples/tagged_pdf_xml_poc/outputs/`
- Verify: `samples/tagged_pdf_xml_poc/outputs/<run-name>/semantic_document.md`
- Verify: `samples/tagged_pdf_xml_poc/outputs/<run-name>/semantic_document.xml`
- Verify: `samples/tagged_pdf_xml_poc/outputs/<run-name>/raw_structure.xml`
- Verify: `samples/tagged_pdf_xml_poc/outputs/<run-name>/extraction_report.json`

- [ ] **Step 1: Run the complete POC suite in required-sample mode**

같은 shell에서 Task 8의 ZC/ZG/KR 환경변수를 유지한 뒤 실행한다. 전체 코드 테스트에서는 ZA/XY 실물 PDF test node 두 개만 명시적으로 제외하고 나머지 unit/behavior tests를 모두 실행한다.

```powershell
.\.venv\Scripts\python -m pytest tests -q `
  --deselect tests/test_layout_regression.py::test_za_retains_complete_structure_and_clean_page_text `
  --deselect tests/test_layout_regression.py::test_xy_retains_structure_without_zg_display_rules
.\.venv\Scripts\python -m compileall src tests
```

Expected: unit/behavior suite와 ZC/ZG/KR integration이 통과한다. ZA/XY real-PDF node는 명시적으로 deselect되며, 기존 Windows symbolic-link capability test만 OS가 symlink를 만들 수 없을 때 skip될 수 있다. ZC/ZG/KR PDF test는 skip되면 안 된다.

- [ ] **Step 2: Regenerate three timestamped review bundles**

충돌 없는 고정 실행 이름을 사용한다.

```powershell
.\.venv\Scripts\tagged-pdf-extract.exe "$env:TAGGED_PDF_ZG_SAMPLE" --output "outputs\readability_review_zg_260906" --overwrite
.\.venv\Scripts\tagged-pdf-extract.exe "$env:TAGGED_PDF_ZC_SAMPLE" --output "outputs\readability_review_zc_260906" --overwrite
.\.venv\Scripts\tagged-pdf-extract.exe "$env:TAGGED_PDF_KR_SAMPLE" --output "outputs\readability_review_kr_260906" --overwrite
```

각 명령의 종료 코드와 `extraction_report.json`의 `status`를 확인한다. `outputs/`는 Git에 추가하지 않는다.

- [ ] **Step 3: Perform output evidence checks**

작은 검증 스크립트 또는 pytest helper로 다음을 출력한다.

- 각 bundle 네 파일 존재와 non-empty 여부;
- Semantic XML의 `sentence-break-source`, `inline-icon`, 기존 ZG 표시 role 수;
- Raw XML의 display attribute 수가 0인지;
- ZG Markdown에서 네 문장 FRA bullet, 세 문장 DEU cell, `[아이콘]`, `※ Cette adresse` 시작 문장, `UK ※ 2025-10-31`의 1-based line numbers;
- ZC/KR의 `[아이콘]`은 각각 대응 Semantic XML evidence와 개수가 같은지;
- `Ł`, `Œ`, `[CONTROL U+0003]` 형태의 표시 재발 여부.

검토자에게는 세 `semantic_document.md` 절대 경로와 위 ZG line numbers를 전달한다.

- [ ] **Step 4: Run repository-required compile verification**

Run from repository root:

```powershell
.\.venv\Scripts\python -m compileall src tests scripts apps
git diff --check
git status --short
```

POC 가상환경과 루트 가상환경이 다르면 루트에서 기존 프로젝트 Python 실행 경로를 사용한다. compile 결과와 diff whitespace 검사를 기록하고, 사용자 소유의 unrelated 변경·stash·untracked sample link/tmp는 수정하거나 삭제하지 않는다.

- [ ] **Step 5: Request code review, address findings, and commit final documentation adjustments**

`requesting-code-review` skill로 승인 설계, 이 계획, 실제 diff, focused/full test evidence를 대조한다. 발견 사항은 `receiving-code-review` 절차로 재현한 뒤 필요한 것만 TDD로 수정한다. 수정이 있으면 관련 focused tests와 전체 POC suite를 다시 실행한다.

Commit: `Complete semantic Markdown readability review`

## Explicit Non-Changes

- bracketed model labels의 Markdown editor 색상 차이를 고치기 위한 escaping/style 처리를 추가하지 않는다.
- icon 이름(Home, Settings 등), OCR, Tesseract, 이미지 catalog/similarity를 추가하지 않는다.
- buyer/language/title 문자열로 sentence/icon 규칙을 dispatch하거나 하드코딩하지 않는다.
- source list item, paragraph, table row/cell을 분할하지 않는다.
- raw PDF text, raw XML, MCID, object-ref, BBox source attributes를 수정하지 않는다.
- 기존 ZG RF/DoC, 번호형 heading, subtitle 규칙을 공용 가독성 detector로 옮기지 않는다.
