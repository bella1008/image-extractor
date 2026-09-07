# Cross-Buyer Inline Icon Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OSD 메뉴 경로와 일반 인라인 아이콘을 바이어·언어 문구·고정 글자 크기 하드코딩 없이 일관되게 `[아이콘]`으로 판별한다.

**Architecture:** 기존 인라인 flow tokenization을 유지하고 판별만 두 경로로 나눈다. 반복된 `>`와 후보 인접성을 사용하는 navigation-route 경로는 flow 전체의 상대 글자 크기를 보조 근거로 사용하고, 나머지는 더 엄격한 generic-inline 경로를 사용한다. 판별 사유와 경로 근거는 model → XML → Markdown validator까지 동일하게 전달하고 재검증한다.

**Tech Stack:** Python 3.11+, frozen dataclasses, `xml.etree.ElementTree`, pytest, 기존 `tagged_pdf_extractor` POC CLI

---

## 파일 책임과 변경 범위

- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/inline_icon_policy.py`: 판별 사유별 상수, 허용 비율, 공통 정책 조회 함수.
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`: navigation-route 감사 근거를 포함하는 `InlineIconHint`.
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/readability_formatting.py`: flow 주변 문장부호 분석, 대표 글자 크기 계산, 두 경로 판별.
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/display_hint_validation.py`: 생성된 hint와 재탐지 결과의 완전 일치 검증.
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py`: 경로별 XML 근거 직렬화.
- `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`: 경로별 XML 근거와 허용 비율 검증, 동일 `[아이콘]` 렌더링.
- `samples/tagged_pdf_xml_poc/tests/test_readability_formatting.py`: 판별기 단위 테스트.
- `samples/tagged_pdf_xml_poc/tests/test_display_hint_validation.py`: dataclass 및 재탐지 일치 테스트.
- `samples/tagged_pdf_xml_poc/tests/test_xml_writer.py`: XML 직렬화 테스트.
- `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`: XML 소비·방어 검증 테스트.
- `samples/tagged_pdf_xml_poc/tests/readability_assertions.py`: 실물 산출물의 reason별 근거 대조.
- `samples/tagged_pdf_xml_poc/tests/test_layout_regression.py`: ZG·ZC·KR 및 선택 실행 ZA·XY 실물 회귀.

### Task 1: 판별 정책과 감사 모델 확장

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/inline_icon_policy.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_readability_formatting.py`

- [ ] **Step 1: 판별 사유별 정책의 실패 테스트 작성**

`test_readability_formatting.py`에 다음 계약을 추가한다.

```python
from tagged_pdf_extractor.domain.inline_icon_policy import (
    GENERIC_INLINE_ICON_REASON,
    NAVIGATION_ROUTE_INLINE_ICON_REASON,
    inline_icon_ratio_limits,
)


def test_inline_icon_ratio_limits_are_reason_specific() -> None:
    assert inline_icon_ratio_limits(GENERIC_INLINE_ICON_REASON) == (3.0, 2.0)
    assert inline_icon_ratio_limits(NAVIGATION_ROUTE_INLINE_ICON_REASON) == (
        5.0,
        2.5,
    )


def test_inline_icon_ratio_limits_reject_unknown_reason() -> None:
    with pytest.raises(ValueError, match="unknown inline icon reason"):
        inline_icon_ratio_limits("manual")
```

`InlineIconHint`의 경로 근거 계약 테스트도 추가한다.

```python
def test_navigation_icon_hint_retains_route_audit_evidence() -> None:
    hint = InlineIconHint(
        child_path=(1, 2),
        page_index=0,
        bbox=(0.0, 0.0, 9.0, 9.0),
        reference_font_size=6.5,
        width_ratio=9.0 / 6.5,
        height_ratio=9.0 / 6.5,
        reason=NAVIGATION_ROUTE_INLINE_ICON_REASON,
        route_separator_count=4,
        route_parenthesized=True,
    )
    assert hint.route_separator_count == 4
    assert hint.route_parenthesized is True
```

- [ ] **Step 2: 테스트를 실행해 현재 API 부재로 실패하는지 확인**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_readability_formatting.py -k "ratio_limits or route_audit" -v
```

Expected: 새 상수·함수 또는 dataclass 필드가 없어 collection 또는 assertion이 FAIL.

- [ ] **Step 3: 최소 정책 API와 모델 구현**

`inline_icon_policy.py`에 호환 alias를 유지하면서 정책을 추가한다.

```python
GENERIC_INLINE_ICON_REASON = "small_inline_figure_with_adjacent_text"
NAVIGATION_ROUTE_INLINE_ICON_REASON = "navigation_route_inline_figure"
INLINE_ICON_REASON = GENERIC_INLINE_ICON_REASON

MAX_INLINE_ICON_WIDTH_FONT_RATIO = 3.0
MAX_INLINE_ICON_HEIGHT_FONT_RATIO = 2.0
MAX_NAVIGATION_ICON_WIDTH_FONT_RATIO = 5.0
MAX_NAVIGATION_ICON_HEIGHT_FONT_RATIO = 2.5


def inline_icon_ratio_limits(reason: str) -> tuple[float, float]:
    if reason == GENERIC_INLINE_ICON_REASON:
        return (
            MAX_INLINE_ICON_WIDTH_FONT_RATIO,
            MAX_INLINE_ICON_HEIGHT_FONT_RATIO,
        )
    if reason == NAVIGATION_ROUTE_INLINE_ICON_REASON:
        return (
            MAX_NAVIGATION_ICON_WIDTH_FONT_RATIO,
            MAX_NAVIGATION_ICON_HEIGHT_FONT_RATIO,
        )
    raise ValueError(f"unknown inline icon reason: {reason}")
```

`models.py`의 hint에 선택적 감사 근거를 추가한다. generic hint는 기존 생성 코드를 깨지 않도록 기본값 `None`을 사용한다.

```python
@dataclass(frozen=True)
class InlineIconHint:
    child_path: tuple[int, ...]
    page_index: int
    bbox: tuple[float, float, float, float]
    reference_font_size: float
    width_ratio: float
    height_ratio: float
    reason: str = INLINE_ICON_REASON
    route_separator_count: int | None = None
    route_parenthesized: bool | None = None
```

- [ ] **Step 4: 정책 테스트와 기존 icon 테스트 실행**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_readability_formatting.py -k "inline_icon or ratio_limits or route_audit" -v
```

Expected: PASS.

- [ ] **Step 5: 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/inline_icon_policy.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py samples/tagged_pdf_xml_poc/tests/test_readability_formatting.py
git commit -m "refactor: define reason-specific inline icon policy"
```

### Task 2: navigation-route 및 robust flow font 판별 구현

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/readability_formatting.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_readability_formatting.py`

- [ ] **Step 1: 실제 실패 유형을 재현하는 테스트 작성**

다음 케이스를 fixture helper를 사용해 추가한다.

```python
def test_navigation_route_uses_flow_font_instead_of_one_point_neighbor() -> None:
    document = _document(
        _element(
            "paragraph",
            _styled_fragment("(", font_sizes=(6.5,), mcid=201),
            _figure(),
            _styled_fragment(
                " > left directional button > ",
                font_sizes=(1.0,),
                mcid=202,
            ),
            _figure(),
            _styled_fragment(
                " Settings > Support)",
                font_sizes=(6.5,),
                mcid=203,
            ),
        )
    )

    hints = detect_inline_icon_hints(document)

    assert len(hints) == 2
    assert all(
        hint.reason == NAVIGATION_ROUTE_INLINE_ICON_REASON for hint in hints
    )
    assert all(hint.reference_font_size == 6.5 for hint in hints)
    assert all(hint.route_separator_count == 3 for hint in hints)
    assert all(hint.route_parenthesized is True for hint in hints)
```

아래 방어 테스트도 작성한다. 기존 `_document`, `_element`, `_figure`,
`_styled_fragment` helper를 그대로 사용한다.

```python
def _inline_paragraph_document(*children: object) -> TaggedDocument:
    return _document(_element("paragraph", *children))


def test_navigation_route_accepts_unparenthesized_icon_start() -> None:
    document = _inline_paragraph_document(
        _figure(),
        _styled_fragment(" > left > ", mcid=204),
        _figure(),
        _styled_fragment(" Settings > Support", mcid=205),
    )
    hints = detect_inline_icon_hints(document)
    assert len(hints) == 2
    assert {hint.reason for hint in hints} == {
        NAVIGATION_ROUTE_INLINE_ICON_REASON
    }
    assert {hint.route_parenthesized for hint in hints} == {False}


def test_navigation_route_accepts_elongated_24_by_9_button_icon() -> None:
    document = _inline_paragraph_document(
        _styled_fragment("Open > ", mcid=206),
        _figure(bbox_value="[100.0, 200.0, 124.0, 209.0]"),
        _styled_fragment(" > Down > Close", mcid=207),
    )
    hint = detect_inline_icon_hints(document)[0]
    assert hint.reason == NAVIGATION_ROUTE_INLINE_ICON_REASON
    assert hint.width_ratio == 24.0 / 6.5


def test_single_separator_does_not_enable_navigation_route() -> None:
    document = _inline_paragraph_document(
        _styled_fragment("Before > ", mcid=208),
        _figure(),
        _styled_fragment(" After", mcid=209),
    )
    hint = detect_inline_icon_hints(document)[0]
    assert hint.reason == GENERIC_INLINE_ICON_REASON
    assert hint.route_separator_count is None


def test_distant_separator_does_not_classify_unrelated_figure() -> None:
    document = _inline_paragraph_document(
        _styled_fragment("Before ", mcid=210),
        _figure(),
        _styled_fragment(" After. Compare A > B > C.", mcid=211),
    )
    hint = detect_inline_icon_hints(document)[0]
    assert hint.reason == GENERIC_INLINE_ICON_REASON


def test_parentheses_without_repeated_separator_do_not_enable_route() -> None:
    document = _inline_paragraph_document(
        _styled_fragment("(", mcid=212),
        _figure(),
        _styled_fragment(" note)", mcid=213),
    )
    hint = detect_inline_icon_hints(document)[0]
    assert hint.reason == GENERIC_INLINE_ICON_REASON


def test_navigation_route_rejects_figure_above_route_ratio_limit() -> None:
    document = _inline_paragraph_document(
        _styled_fragment("Open > ", mcid=214),
        _figure(bbox_value="[100.0, 200.0, 132.50001, 209.0]"),
        _styled_fragment(" > Down > Close", mcid=215),
    )
    assert detect_inline_icon_hints(document) == ()


def test_generic_inline_icon_uses_contiguous_flow_median_font() -> None:
    document = _inline_paragraph_document(
        _styled_fragment("Near", font_sizes=(1.0,), mcid=216),
        _figure(),
        _styled_fragment(
            " ordinary body text",
            font_sizes=(6.5,),
            mcid=217,
        ),
    )
    hint = detect_inline_icon_hints(document)[0]
    assert hint.reason == GENERIC_INLINE_ICON_REASON
    assert hint.reference_font_size == 6.5
```

`distant_separator` fixture는 문장 종결부호 또는 구조 barrier 뒤의 `>`가 후보의 local route segment에 포함되지 않는 구조로 만든다.

- [ ] **Step 2: 새 테스트가 현재 detector에서 실패하는지 확인**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_readability_formatting.py -k "navigation_route or contiguous_flow_median" -v
```

Expected: navigation reason/근거가 없거나 기존 3.0/2.0 비율 때문에 FAIL.

- [ ] **Step 3: 후보 로컬 경로 분석 helper 구현**

`readability_formatting.py`에 내부 근거 타입과 helper를 추가한다.

```python
@dataclass(frozen=True)
class _NavigationRouteEvidence:
    separator_count: int
    parenthesized: bool
    reference_font_size: float


def _is_separator_adjacent(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(">") or stripped.endswith(">")
```

`_navigation_route_evidence(flow, index, page_index)`는 다음 순서로 동작한다.

1. candidate 주변에서 구조적으로 연속된 same-page fragment/figure segment를 선택한다.
2. candidate의 가장 가까운 visible 좌우 fragment 중 한쪽 이상에 `_is_separator_adjacent()`가 참인지 확인한다.
3. 후보를 감싸는 가장 가까운 `(` … `)` 범위가 있으면 그 범위를 local window로 사용하고 `parenthesized=True`로 기록한다.
4. 괄호 범위가 없으면 sentence terminator 또는 flow 끝까지의 candidate-local window를 사용한다.
5. window의 ASCII `>` 개수가 2 미만이면 `None`을 반환한다.
6. same-page visible fragment 전체의 `_visible_font_size_weights()`를 모아 `_weighted_median()`을 계산한다. 유효한 근거가 없거나 fragment style이 불완전하면 `None`을 반환한다.

문구 문자열이나 언어 코드는 검사하지 않는다.

- [ ] **Step 4: 두 경로 판별을 `_inline_icon_hint()`에 연결**

공통 BBox·page·visible figure text 검사를 먼저 수행한다. 그 뒤 다음 형태로 reason과 기준 글자 크기를 선택한다.

```python
route = _navigation_route_evidence(flow, index, figure.page_index)
if route is not None:
    reason = NAVIGATION_ROUTE_INLINE_ICON_REASON
    reference_font_size = route.reference_font_size
else:
    reason = GENERIC_INLINE_ICON_REASON
    reference_font_size = _generic_flow_reference_font_size(
        flow,
        index,
        figure.page_index,
    )
    if reference_font_size is None:
        return None

max_width_ratio, max_height_ratio = inline_icon_ratio_limits(reason)
width_ratio = width / reference_font_size
height_ratio = height / reference_font_size
if width_ratio > max_width_ratio or height_ratio > max_height_ratio:
    return None

return InlineIconHint(
    child_path=candidate.child_path,
    page_index=figure.page_index,
    bbox=bbox,
    reference_font_size=reference_font_size,
    width_ratio=width_ratio,
    height_ratio=height_ratio,
    reason=reason,
    route_separator_count=(route.separator_count if route else None),
    route_parenthesized=(route.parenthesized if route else None),
)
```

generic 경로는 인라인 여부를 증명하기 위해 기존처럼 좌우 중 한쪽 이상의 visible adjacent fragment를 요구하되, 크기 중앙값은 same-page contiguous segment 전체에서 계산한다.

- [ ] **Step 5: focused domain 테스트 실행**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_readability_formatting.py tests/test_display_hint_validation.py -v
```

Expected: PASS.

- [ ] **Step 6: 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/readability_formatting.py samples/tagged_pdf_xml_poc/tests/test_readability_formatting.py
git commit -m "feat: detect navigation route inline icons"
```

### Task 3: XML 근거 직렬화와 Markdown 방어 검증

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py`
- Modify: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/display_hint_validation.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_xml_writer.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py`
- Test: `samples/tagged_pdf_xml_poc/tests/test_display_hint_validation.py`

- [ ] **Step 1: navigation-route XML round-trip 실패 테스트 작성**

`test_xml_writer.py`에서 navigation hint를 만들고 다음 속성을 단언한다.

```python
assert inline_icon.attrib["icon-reason"] == "navigation_route_inline_figure"
assert inline_icon.attrib["route-separator-count"] == "3"
assert inline_icon.attrib["route-parenthesized"] == "true"
assert inline_icon.attrib["reference-font-size"] == "6.5"
```

`test_markdown_writer.py`의 `_inline_icon_element()` helper가 reason별 속성을 만들 수 있게 한 뒤 아래를 추가한다.

```python
def test_navigation_route_icon_renders_neutral_icon_token(tmp_path: Path) -> None:
    xml = _paragraph_xml(
        _inline_icon_element(
            reason="navigation_route_inline_figure",
            bbox="[100, 200, 124, 209]",
            reference_font_size="6.5",
            width_ratio=str(24 / 6.5),
            height_ratio=str(9 / 6.5),
            route_separator_count="3",
            route_parenthesized="true",
        )
    )
    assert "[아이콘]" in _render_xml(tmp_path, xml)
```

다음 오류를 각각 거부하는 parameterized 테스트를 추가한다.

- route reason인데 `route-separator-count`가 없음
- count가 `0`, `1`, 음수, 소수 또는 boolean 문자열
- `route-parenthesized`가 `true|false` 이외의 값
- generic reason에 route 전용 속성이 있음
- navigation reason이 generic 비율은 넘지만 5.0/2.5 안이면 허용
- navigation reason이 5.0 또는 2.5를 초과함
- 알 수 없는 reason

- [ ] **Step 2: 직렬화·Markdown 테스트가 실패하는지 확인**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_xml_writer.py tests/test_markdown_writer.py -k "inline_icon or navigation_route" -v
```

Expected: route 속성 미지원 또는 reason 거부로 FAIL.

- [ ] **Step 3: XML writer에 reason별 근거 직렬화 구현**

`_inline_icon_attributes()`는 공통 속성을 만든 뒤 navigation reason에만 다음을 추가한다.

```python
if hint.reason == NAVIGATION_ROUTE_INLINE_ICON_REASON:
    if (
        type(hint.route_separator_count) is not int
        or hint.route_separator_count < 2
        or type(hint.route_parenthesized) is not bool
    ):
        raise ValueError("invalid navigation route icon evidence")
    attributes["route-separator-count"] = str(hint.route_separator_count)
    attributes["route-parenthesized"] = (
        "true" if hint.route_parenthesized else "false"
    )
elif (
    hint.route_separator_count is not None
    or hint.route_parenthesized is not None
):
    raise ValueError("generic inline icon contains route evidence")
```

- [ ] **Step 4: Markdown validator를 reason별 정책으로 변경**

고정 `INLINE_ICON_REASON` 비교와 단일 비율 상한 대신 다음 정책을 사용한다.

```python
try:
    max_width_ratio, max_height_ratio = inline_icon_ratio_limits(reason)
except ValueError as exc:
    raise ValueError("invalid inline-icon icon-reason") from exc
```

navigation reason은 count가 정수 2 이상인지, parenthesized가 정확히 `true|false`인지 확인한다. generic reason은 route 전용 속성을 거부한다. BBox 대비 직렬화된 비율 재계산과 visible-text 거부는 그대로 유지한다.

`_SemanticInlineIconEvidence`에도 reason과 route 근거를 보관해 구조 검증 단계에서 손실되지 않게 한다.

- [ ] **Step 5: domain hint validation에 reason별 불변조건 추가**

`display_hint_validation.py`에서 `inline_icon_ratio_limits(hint.reason)`을 호출해 reason을 검증하고, navigation reason에는 route count/boolean을 요구하며 generic reason에는 두 필드가 모두 `None`인지 검사한다. 마지막에는 기존처럼 detector 결과와 dataclass의 완전 일치를 요구한다.

- [ ] **Step 6: 관련 writer/validator 테스트 전체 실행**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_xml_writer.py tests/test_markdown_writer.py tests/test_display_hint_validation.py -v
```

Expected: PASS.

- [ ] **Step 7: 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/markdown_writer.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/display_hint_validation.py samples/tagged_pdf_xml_poc/tests/test_xml_writer.py samples/tagged_pdf_xml_poc/tests/test_markdown_writer.py samples/tagged_pdf_xml_poc/tests/test_display_hint_validation.py
git commit -m "feat: preserve navigation icon evidence in XML"
```

### Task 4: 실물 PDF 회귀 계약 강화

**Files:**
- Modify: `samples/tagged_pdf_xml_poc/tests/readability_assertions.py`
- Modify: `samples/tagged_pdf_xml_poc/tests/test_layout_regression.py`

- [ ] **Step 1: 산출물 reason별 근거 검사 추가**

`assert_inline_icon_evidence_matches_detector()`에서 XML의 `icon-reason`을 detector hint와 비교한다. navigation reason이면 다음도 비교한다.

```python
assert int(element.attrib["route-separator-count"]) == (
    hint.route_separator_count
)
assert (element.attrib["route-parenthesized"] == "true") is (
    hint.route_parenthesized
)
```

generic reason이면 route 전용 XML 속성이 없음을 단언한다. model hint 수, XML inline-icon 수, Markdown `[아이콘]` 수의 기존 동일성 검사는 유지한다.

- [ ] **Step 2: 문의한 경로의 회귀 assertion 작성**

ZG·ZC·KR 실물 테스트에 문구 전체 일치를 하드코딩하지 않고 구조를 검사하는 helper를 추가한다.

```python
def _assert_repeated_navigation_routes_use_icons(root: ET.Element) -> None:
    for flow in _navigation_route_flows(root):
        assert flow.separator_count >= 2
        assert flow.figure_count >= 1
        assert flow.inline_icon_count == flow.figure_count
```

`_navigation_route_flows()`는 paragraph/list-body의 로컬 `>` 구간만 반환하고 source token, 언어, Settings 등의 단어를 검사하지 않는다. ZG, ZC, KR 필수 샘플에 적용하고 ZA·XY optional 실물 테스트에도 동일 helper를 적용한다.

- [ ] **Step 3: 실물 테스트가 현재 산출에서 실패하는지 확인**

Run:

```powershell
$env:TAGGED_PDF_REQUIRE_SAMPLES = "1"
$env:TAGGED_PDF_ZC_SAMPLE = (Resolve-Path "..\SUG_RAW\TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf").Path
$env:TAGGED_PDF_ZG_SAMPLE = (Resolve-Path "..\SUG_RAW\TV_ZG\BN68-25448A-00_SUG_Y26 TV ALL_ZG XN ZT_L05_260204.0.pdf").Path
$env:TAGGED_PDF_KR_SAMPLE = (Resolve-Path "..\SUG_RAW\TV_KR\BN68-25108A-00_SUG_Y26 TV ALL_KR_KOR_251218.0.pdf").Path
.\.venv\Scripts\python -m pytest tests/test_layout_regression.py -k "zc or zg or kr" -v
```

Expected: 기존에 `[그림: 텍스트 없음]`으로 남은 route figure 때문에 FAIL.

- [ ] **Step 4: 새 detector로 ZG·ZC·KR 회귀 통과 확인**

같은 명령을 다시 실행한다.

Expected: PASS이며 세 `extraction_report.json` 모두 `status=pass`.

- [ ] **Step 5: ZA·XY 선택 회귀 실행**

```powershell
$env:TAGGED_PDF_ZA_SAMPLE = (Resolve-Path "..\SUG_RAW\TV_ZA\BN68-25099A-00_SUG_Y26 TV ALL_ZA_ENG_251217.0.pdf").Path
$env:TAGGED_PDF_XY_SAMPLE = (Resolve-Path "..\SUG_RAW\TV_XY\BN68-25031B-00_SUG_Y26 TV ALL_XY_ENG_251229.0.pdf").Path
.\.venv\Scripts\python -m pytest tests/test_layout_regression.py -k "za or xy" -v
```

Expected: PASS. ZA·XY도 별도 dispatch 없이 같은 navigation reason을 사용한다.

- [ ] **Step 6: 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/tests/readability_assertions.py samples/tagged_pdf_xml_poc/tests/test_layout_regression.py
git commit -m "test: gate navigation icons across buyer samples"
```

### Task 5: 검토 산출물 생성과 최종 검증

**Files:**
- Generated, ignored: `samples/tagged_pdf_xml_poc/outputs/navigation_icon_review_*_260907/`
- Modify if required by verified behavior only: `samples/tagged_pdf_xml_poc/README.md`

- [ ] **Step 1: ZG·ZC·KR 검토 bundle 재생성**

각 샘플에 현재 CLI를 실행한다.

```powershell
.\.venv\Scripts\tagged-pdf-extract.exe "$env:TAGGED_PDF_ZG_SAMPLE" --output "outputs\navigation_icon_review_zg_260907" --overwrite
.\.venv\Scripts\tagged-pdf-extract.exe "$env:TAGGED_PDF_ZC_SAMPLE" --output "outputs\navigation_icon_review_zc_260907" --overwrite
.\.venv\Scripts\tagged-pdf-extract.exe "$env:TAGGED_PDF_KR_SAMPLE" --output "outputs\navigation_icon_review_kr_260907" --overwrite
```

Expected: 세 명령 모두 exit code `0`, report `status=pass`.

- [ ] **Step 2: 사람 검토용 핵심 지점 확인**

- ZG 기존 MD 27~29, 438~454, 464~466에 대응하는 새 경로에서 모든 실제 OSD 그림이 `[아이콘]`인지 확인한다.
- ZC의 Internet security 및 Troubleshooting OSD 경로를 확인한다.
- KR의 사용자 설명서·설정 OSD 경로를 확인한다.
- Wall-anchor 같은 비경로 인라인 아이콘이 계속 `[아이콘]`인지 확인한다.
- 독립 그림과 안전 심볼 표가 무리하게 전부 `[아이콘]`으로 바뀌지 않았는지 확인한다.

- [ ] **Step 3: 산출물 정합성 자동 점검**

각 bundle에 대해 다음을 검사한다.

- semantic model hint 수 = XML `display-role="inline-icon"` 수
- XML inline icon 수 = Markdown `[아이콘]` 수
- Raw XML에는 display 속성이 없음
- `Ł`, `Œ`, `[CONTROL U+0003]`가 없음
- sentence break 수와 기존 검토 baseline이 동일함
- headings/lists/tables/RF/DoC 관련 기존 assertion이 모두 통과함

- [ ] **Step 4: 전체 테스트와 compileall 실행**

```powershell
.\.venv\Scripts\python -m pytest tests -q
.\.venv\Scripts\python -m compileall src tests
```

Expected: pytest PASS(환경상 Windows symlink 테스트만 skip 가능), compileall exit code `0`.

- [ ] **Step 5: README 감사 설명 갱신**

실제 결과가 설계와 일치할 때만 README의 아이콘 설명을 다음 의미로 갱신한다.

```text
[아이콘]은 이름 판별 결과가 아니다. 반복된 OSD 경로 구분자와 inline 구조,
또는 일반 inline 구조와 상대 크기 근거로 판별한 이름 없는 figure 표시다.
판별 reason과 상대 크기 근거는 semantic XML에 보존된다.
```

- [ ] **Step 6: 최종 변경 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/README.md
git commit -m "docs: record cross-buyer navigation icon policy"
```

- [ ] **Step 7: 최종 diff 확인**

```powershell
git status --short
git diff main...HEAD --check
git log --oneline main..HEAD
```

Expected: tracked worktree clean, whitespace 오류 없음, 이번 기능의 설계·구현·테스트·문서 커밋만 표시됨.
