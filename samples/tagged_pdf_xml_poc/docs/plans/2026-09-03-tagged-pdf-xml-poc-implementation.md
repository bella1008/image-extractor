# Tagged PDF XML Extraction POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tagged PDF의 논리 구조와 MCID 텍스트를 독립적으로 복원하여 원시 XML, 의미 XML, 품질 리포트를 생성하고 지정된 ZC PDF에서 추출 품질을 검증한다.

**Architecture:** 상위 프로젝트를 import하지 않는 독립 Python 패키지로 구성한다. Domain 모델과 Application 유스케이스는 PDF 라이브러리를 모르며, `pypdf` 태그 리더와 `PyMuPDF` 기준 텍스트 추출기, XML/JSON 출력기는 Port를 구현하는 Infrastructure 어댑터로 둔다.

**Tech Stack:** Python 3.11+, pypdf, PyMuPDF, pytest, 표준 라이브러리 `xml.etree.ElementTree`, `dataclasses`, `typing.Protocol`, `difflib`

---

## 파일 구조

```text
samples/tagged_pdf_xml_poc/
  pyproject.toml
  README.md
  src/tagged_pdf_extractor/
    __init__.py
    cli.py
    domain/
      __init__.py
      models.py
      role_mapping.py
      text_joining.py
    application/
      __init__.py
      extract_document.py
      evaluate_quality.py
    ports/
      __init__.py
      pdf_reader.py
      baseline_reader.py
      output_writer.py
    infrastructure/
      __init__.py
      mcid_text.py
      pypdf_reader.py
      pymupdf_baseline.py
      xml_writer.py
      json_report_writer.py
      output_bundle.py
  tests/
    test_project_isolation.py
    test_role_mapping.py
    test_text_joining.py
    test_mcid_text.py
    test_pypdf_reader.py
    test_xml_writer.py
    test_quality_evaluator.py
    test_output_bundle.py
    test_cli.py
    test_zc_integration.py
```

이 계획은 1단계 범위만 구현한다. XML-to-Markdown, OCR, 체크리스트, 다국어 의미
비교, UI, 바이어별 보정 규칙은 파일이나 숨은 fallback 형태로도 추가하지 않는다.
상위 프로젝트 `src`와의 단절은 Task 1의 계약 테스트와 최종 Git 범위 검사로
검증한다.

### Task 1: 독립 패키지 골격과 격리 계약

**Files:**
- Create: `samples/tagged_pdf_xml_poc/pyproject.toml`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/__init__.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/__init__.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/__init__.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/ports/__init__.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/__init__.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_project_isolation.py`

- [ ] **Step 1: 상위 프로젝트 import를 금지하는 실패 테스트 작성**

```python
from pathlib import Path
import tagged_pdf_extractor


def test_poc_source_does_not_import_parent_src_package() -> None:
    project_root = Path(__file__).parents[1]
    assert (project_root / "pyproject.toml").is_file()
    assert tagged_pdf_extractor.__version__ == "0.1.0"
    offenders = []
    for path in (project_root / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "from src" in text or "import src" in text:
            offenders.append(path.relative_to(project_root).as_posix())
    assert offenders == []
```

- [ ] **Step 2: 테스트를 실행해 패키지 골격 부재로 실패하는지 확인**

Run: `cd samples/tagged_pdf_xml_poc && python -m pytest tests/test_project_isolation.py -v`

Expected: FAIL 또는 수집 오류. 아직 `pyproject.toml`과 설치 가능한 패키지가 없다.

- [ ] **Step 3: 최소 패키지 설정 작성**

```toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "tagged-pdf-xml-poc"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "pypdf>=6,<7",
  "PyMuPDF>=1.26,<2",
]

[project.optional-dependencies]
dev = ["pytest>=8,<9"]

[project.scripts]
tagged-pdf-extract = "tagged_pdf_extractor.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```

각 `__init__.py`는 UTF-8 빈 모듈로 생성하고 최상위 모듈에는 다음 버전만 둔다.

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: 독립 가상환경에 설치하고 테스트 통과 확인**

Run: `cd samples/tagged_pdf_xml_poc && python -m venv .venv`

Run: `cd samples/tagged_pdf_xml_poc && .venv\Scripts\python -m pip install -e ".[dev]"`

Run: `cd samples/tagged_pdf_xml_poc && .venv\Scripts\python -m pytest tests/test_project_isolation.py -v`

Expected: `1 passed`.

- [ ] **Step 5: 골격 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/pyproject.toml samples/tagged_pdf_xml_poc/src samples/tagged_pdf_xml_poc/tests/test_project_isolation.py
git commit -m "Scaffold independent tagged PDF extractor"
```

### Task 2: Domain 모델과 표준 역할 매핑

**Files:**
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/models.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/role_mapping.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_role_mapping.py`

- [ ] **Step 1: 역할 매핑과 불변 트리 모델의 실패 테스트 작성**

```python
from tagged_pdf_extractor.domain.models import ContentFragment, StructureElement
from tagged_pdf_extractor.domain.role_mapping import map_role


def test_maps_headings_and_preserves_unknown_source_role() -> None:
    assert map_role("H2", {}) == ("heading", 2)
    assert map_role("CustomHeading", {"CustomHeading": "H3"}) == ("heading", 3)
    assert map_role("SamsungBox", {}) == ("unknown", None)


def test_structure_element_preserves_mixed_child_order() -> None:
    first = ContentFragment(page_index=0, mcid=3, text_parts=("A",))
    nested = StructureElement(source_role="Span", semantic_role="span")
    last = ContentFragment(page_index=0, mcid=4, text_parts=("B",))
    element = StructureElement(
        source_role="P", semantic_role="paragraph", children=(first, nested, last)
    )
    assert element.children == (first, nested, last)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv\Scripts\python -m pytest tests/test_role_mapping.py -v`

Expected: FAIL with missing `domain.models` and `domain.role_mapping`.

- [ ] **Step 3: 불변 모델과 역할 매핑 구현**

```python
# domain/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class Diagnostic:
    severity: Literal["warning", "error"]
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentFragment:
    page_index: int
    mcid: int | None
    text_parts: tuple[str, ...]
    object_ref: str | None = None

    @property
    def text(self) -> str:
        return "".join(self.text_parts)


@dataclass(frozen=True)
class StructureElement:
    source_role: str
    semantic_role: str
    heading_level: int | None = None
    object_ref: str | None = None
    page_index: int | None = None
    title: str | None = None
    language: str | None = None
    alternate_text: str | None = None
    actual_text: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()
    children: tuple[StructureElement | ContentFragment, ...] = ()


@dataclass(frozen=True)
class TaggedDocument:
    source_path: Path
    marked: bool
    language: str | None
    role_map: tuple[tuple[str, str], ...]
    children: tuple[StructureElement | ContentFragment, ...]
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class QualityReport:
    status: Literal["pass", "fail"]
    metrics: dict[str, Any]
    hard_gates: dict[str, bool]
    diagnostics: tuple[Diagnostic, ...]
    join_decisions: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ExtractionArtifacts:
    raw_xml: Path
    semantic_xml: Path
    report_json: Path
```

```python
# domain/role_mapping.py
ROLE_MAP = {
    "Document": "document", "Part": "part", "Art": "article",
    "Sect": "section", "Div": "division", "P": "paragraph",
    "L": "list", "LI": "list_item", "Lbl": "label",
    "LBody": "list_body", "Table": "table", "TR": "table_row",
    "TH": "table_header", "TD": "table_cell", "Figure": "figure",
    "Caption": "caption", "Span": "span", "Link": "link",
}


def map_role(source_role: str, role_map: dict[str, str]) -> tuple[str, int | None]:
    resolved = role_map.get(source_role, source_role)
    if resolved == "H":
        return "heading", None
    if len(resolved) == 2 and resolved[0] == "H" and resolved[1].isdigit():
        return "heading", int(resolved[1])
    if resolved == "Title":
        return "heading", 1
    return ROLE_MAP.get(resolved, "unknown"), None
```

- [ ] **Step 4: 모델과 매핑 테스트 통과 확인**

Run: `.venv\Scripts\python -m pytest tests/test_role_mapping.py -v`

Expected: `2 passed`.

- [ ] **Step 5: Domain 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain samples/tagged_pdf_xml_poc/tests/test_role_mapping.py
git commit -m "Add tagged document domain model"
```

### Task 3: 보수적 텍스트 연결

**Files:**
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/text_joining.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_text_joining.py`

- [ ] **Step 1: 문장 연속성과 특수문자 보존 실패 테스트 작성**

```python
from tagged_pdf_extractor.domain.text_joining import join_text_parts


def test_joins_wrapped_sentence_without_changing_osd_path() -> None:
    text, decisions = join_text_parts(("Go to Settings > General", " > Accessibility."))
    assert text == "Go to Settings > General > Accessibility."
    assert decisions == ({"boundary": 0, "action": "trim_left"},)


def test_preserves_real_hyphen_and_unicode_arrow() -> None:
    text, _ = join_text_parts(("Wi-Fi", " → Network / Status"))
    assert text == "Wi-Fi → Network / Status"


def test_inserts_space_between_word_fragments() -> None:
    text, decisions = join_text_parts(("This is", "a sentence."))
    assert text == "This is a sentence."
    assert decisions[-1]["action"] == "insert_space"
```

- [ ] **Step 2: 연결 테스트 실패 확인**

Run: `.venv\Scripts\python -m pytest tests/test_text_joining.py -v`

Expected: FAIL with missing `join_text_parts`.

- [ ] **Step 3: 최소 연결 규칙 구현**

```python
from __future__ import annotations

import re


def join_text_parts(parts: tuple[str, ...]) -> tuple[str, tuple[dict[str, object], ...]]:
    if not parts:
        return "", ()
    result = parts[0]
    decisions: list[dict[str, object]] = []
    for index, raw_next in enumerate(parts[1:]):
        previous = result
        next_part = raw_next
        if previous.endswith((" ", "\n", "\t")):
            result = previous.rstrip() + " " + next_part.lstrip()
            action = "normalize_existing_space"
        elif next_part[:1].isspace():
            result = previous + " " + next_part.lstrip()
            action = "trim_left"
        elif re.search(r"[\w\])}]$", previous) and re.match(r"[\w[(]", next_part):
            result = previous + " " + next_part
            action = "insert_space"
        else:
            result = previous + next_part
            action = "keep_adjacent"
        decisions.append({"boundary": index, "action": action})
    return result, tuple(decisions)
```

하이픈 제거 규칙은 1차 구현에 넣지 않는다. 원문 보존이 우선이며 실제 출력에서
레이아웃 하이픈 사례가 확인된 후 별도 테스트와 함께 추가한다.

- [ ] **Step 4: 연결 테스트 통과 확인**

Run: `.venv\Scripts\python -m pytest tests/test_text_joining.py -v`

Expected: `3 passed`.

- [ ] **Step 5: 연결 규칙 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/domain/text_joining.py samples/tagged_pdf_xml_poc/tests/test_text_joining.py
git commit -m "Add conservative tagged text joining"
```

### Task 4: Port 계약과 MCID 텍스트 수집기

**Files:**
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/ports/pdf_reader.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/ports/baseline_reader.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/ports/output_writer.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/mcid_text.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_mcid_text.py`

- [ ] **Step 1: 중첩 marked-content 수집 실패 테스트 작성**

```python
from tagged_pdf_extractor.infrastructure.mcid_text import McidTextCollector


class FakePage:
    def extract_text(self, *, visitor_operand_before, visitor_text):
        visitor_operand_before(b"BDC", ["/P", {"/MCID": 7}], None, None)
        visitor_text("Settings >", None, None, None, 10)
        visitor_operand_before(b"BDC", ["/Span", {}], None, None)
        visitor_text(" General", None, None, None, 10)
        visitor_operand_before(b"EMC", [], None, None)
        visitor_operand_before(b"EMC", [], None, None)
        return "Settings > General"


def test_collects_text_under_inherited_mcid() -> None:
    result = McidTextCollector().collect(FakePage(), page_index=0)
    assert result.parts_by_mcid == {7: ("Settings >", " General")}
    assert result.diagnostics == ()
```

- [ ] **Step 2: MCID 수집 테스트 실패 확인**

Run: `.venv\Scripts\python -m pytest tests/test_mcid_text.py -v`

Expected: FAIL with missing `McidTextCollector`.

- [ ] **Step 3: Port와 MCID 수집기 구현**

```python
# ports/pdf_reader.py
from pathlib import Path
from typing import Protocol
from tagged_pdf_extractor.domain.models import TaggedDocument


class TaggedPdfReaderPort(Protocol):
    def read(self, pdf_path: Path) -> TaggedDocument: ...
```

```python
# ports/baseline_reader.py
from pathlib import Path
from typing import Protocol


class BaselineReaderPort(Protocol):
    def read_text(self, pdf_path: Path) -> str: ...
```

```python
# ports/output_writer.py
from pathlib import Path
from typing import Protocol
from tagged_pdf_extractor.domain.models import ExtractionArtifacts, QualityReport, TaggedDocument


class OutputWriterPort(Protocol):
    def write(
        self, document: TaggedDocument, report: QualityReport,
        output_dir: Path, overwrite: bool = False,
    ) -> ExtractionArtifacts: ...
```

```python
# infrastructure/mcid_text.py
from dataclasses import dataclass
from typing import Any
from tagged_pdf_extractor.domain.models import Diagnostic


@dataclass(frozen=True)
class McidTextResult:
    parts_by_mcid: dict[int, tuple[str, ...]]
    diagnostics: tuple[Diagnostic, ...]


class McidTextCollector:
    def collect(self, page: Any, page_index: int) -> McidTextResult:
        stack: list[int | None] = []
        parts: dict[int, list[str]] = {}
        diagnostics: list[Diagnostic] = []

        def before(operator, operands, _cm, _tm):
            if operator in (b"BMC", b"BDC"):
                mcid = None
                if operator == b"BDC" and len(operands) > 1:
                    properties = operands[1]
                    if hasattr(properties, "get") and properties.get("/MCID") is not None:
                        mcid = int(properties["/MCID"])
                stack.append(mcid if mcid is not None else (stack[-1] if stack else None))
            elif operator == b"EMC":
                if stack:
                    stack.pop()
                else:
                    diagnostics.append(Diagnostic(
                        "warning", "unbalanced_emc", "EMC without matching BMC/BDC",
                        {"page_index": page_index},
                    ))

        def visit_text(text, _cm, _tm, _font, _size):
            if text and stack and stack[-1] is not None:
                parts.setdefault(stack[-1], []).append(text)

        page.extract_text(visitor_operand_before=before, visitor_text=visit_text)
        return McidTextResult(
            {mcid: tuple(values) for mcid, values in parts.items()}, tuple(diagnostics)
        )
```

- [ ] **Step 4: MCID 수집 테스트 통과 확인**

Run: `.venv\Scripts\python -m pytest tests/test_mcid_text.py -v`

Expected: `1 passed`.

- [ ] **Step 5: Port와 수집기 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/ports samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/mcid_text.py samples/tagged_pdf_xml_poc/tests/test_mcid_text.py
git commit -m "Add extraction ports and MCID collector"
```

### Task 5: pypdf 구조 트리 리더

**Files:**
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pypdf_reader.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_pypdf_reader.py`

- [ ] **Step 1: 태그 누락 및 중첩 구조 복원 실패 테스트 작성**

```python
from pathlib import Path
import pytest
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfError, TaggedPdfReader


def test_rejects_pdf_without_structure_tree(tmp_path: Path, monkeypatch) -> None:
    class FakeReader:
        trailer = {"/Root": {"/MarkInfo": {"/Marked": False}}}
        pages = []
    monkeypatch.setattr("tagged_pdf_extractor.infrastructure.pypdf_reader.PdfReader", lambda _: FakeReader())
    with pytest.raises(TaggedPdfError, match="StructTreeRoot"):
        TaggedPdfReader().read(tmp_path / "plain.pdf")


def test_object_reference_is_stable() -> None:
    class Ref:
        idnum = 81
        generation = 0
    assert TaggedPdfReader.object_ref(Ref()) == "81 0 R"
```

- [ ] **Step 2: 리더 테스트 실패 확인**

Run: `.venv\Scripts\python -m pytest tests/test_pypdf_reader.py -v`

Expected: FAIL with missing `TaggedPdfReader`.

- [ ] **Step 3: 구조 트리 순회 구현**

구현은 다음 계약을 정확히 따른다.

```python
class TaggedPdfError(RuntimeError):
    pass


class TaggedPdfReader:
    def __init__(self, collector: McidTextCollector | None = None) -> None:
        self.collector = collector or McidTextCollector()

    @staticmethod
    def resolve(value):
        return value.get_object() if hasattr(value, "get_object") else value

    @staticmethod
    def object_ref(value) -> str | None:
        ref = getattr(value, "indirect_reference", value)
        if hasattr(ref, "idnum"):
            return f"{ref.idnum} {getattr(ref, 'generation', 0)} R"
        return None

    def read(self, pdf_path: Path) -> TaggedDocument:
        reader = PdfReader(str(pdf_path))
        catalog = self.resolve(reader.trailer["/Root"])
        marked = bool(catalog.get("/MarkInfo", {}).get("/Marked", False))
        struct_root = self.resolve(catalog.get("/StructTreeRoot"))
        if struct_root is None:
            raise TaggedPdfError("PDF has no /StructTreeRoot")

        page_indexes = {
            self.object_ref(page.indirect_reference): index
            for index, page in enumerate(reader.pages)
        }
        mcid_text = {}
        diagnostics = []
        for index, page in enumerate(reader.pages):
            result = self.collector.collect(page, index)
            mcid_text[index] = result.parts_by_mcid
            diagnostics.extend(result.diagnostics)

        role_map = {
            str(key).lstrip("/"): str(value).lstrip("/")
            for key, value in struct_root.get("/RoleMap", {}).items()
        }
        children = self._walk_kids(
            struct_root.get("/K", []), None, page_indexes,
            mcid_text, role_map, diagnostics, set(),
        )
        return TaggedDocument(
            source_path=pdf_path, marked=marked,
            language=str(catalog.get("/Lang")) if catalog.get("/Lang") else None,
            role_map=tuple(sorted(role_map.items())), children=tuple(children),
            diagnostics=tuple(diagnostics),
        )
```

`resolve`는 `get_object()`를 가진 indirect object를 실제 PDF 객체로 바꾸고,
직접 객체는 그대로 반환한다. `_walk_kids`도 배열·사전·`/Pg`·`/K`를 읽기 전에
동일한 함수를 사용한다.

`_walk_kids`는 배열 순서를 그대로 유지하며 다음 네 경우를 처리한다.

```text
숫자            -> 현재 상속 페이지의 MCID ContentFragment
/Type /MCR      -> /Pg 또는 상속 페이지의 /MCID ContentFragment
/Type /OBJR     -> unsupported_objr 진단
/S가 있는 사전  -> StructureElement 생성 후 /K 재귀 순회
```

각 재귀 호출은 indirect object reference를 `visited`에 넣어 순환을 감지한다.
페이지는 `/Pg`의 object reference를 `page_indexes`에서 찾아 결정하고 자식에게
상속한다. MCID가 없으면 `unresolved_mcid` 진단과 빈 `text_parts`를 가진 조각을
남겨 원본 구조 순서가 사라지지 않게 한다. `/T`, `/Lang`, `/Alt`, `/ActualText`,
`/A`는 `StructureElement` 필드에 보존한다.

- [ ] **Step 4: 리더 테스트와 기존 테스트 통과 확인**

Run: `.venv\Scripts\python -m pytest tests/test_pypdf_reader.py tests/test_mcid_text.py tests/test_role_mapping.py -v`

Expected: 모든 테스트 PASS.

- [ ] **Step 5: 구조 리더 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pypdf_reader.py samples/tagged_pdf_xml_poc/tests/test_pypdf_reader.py
git commit -m "Traverse tagged PDF structure tree"
```

### Task 6: XML 직렬화와 왕복 보존

**Files:**
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_xml_writer.py`

- [ ] **Step 1: 계층·원본 조각·특수문자 왕복 실패 테스트 작성**

```python
from pathlib import Path
from xml.etree import ElementTree as ET
from tagged_pdf_extractor.domain.models import ContentFragment, StructureElement, TaggedDocument
from tagged_pdf_extractor.infrastructure.xml_writer import XmlDocumentWriter


def test_xml_round_trip_preserves_hierarchy_and_osd_path(tmp_path: Path) -> None:
    fragment = ContentFragment(0, 8, ("Settings > General", " → Accessibility & Help"))
    heading = StructureElement("H2", "heading", heading_level=2, children=(fragment,))
    document = TaggedDocument(tmp_path / "sample.pdf", True, "en", (), (heading,))
    raw_path = tmp_path / "raw.xml"
    semantic_path = tmp_path / "semantic.xml"

    XmlDocumentWriter().write_raw(document, raw_path)
    decisions = XmlDocumentWriter().write_semantic(document, semantic_path)

    assert "".join(ET.parse(raw_path).getroot().itertext()) == fragment.text
    semantic = ET.parse(semantic_path).getroot()
    assert semantic.find("heading").attrib["level"] == "2"
    assert "".join(semantic.itertext()) == "Settings > General → Accessibility & Help"
    assert decisions
```

- [ ] **Step 2: XML 테스트 실패 확인**

Run: `.venv\Scripts\python -m pytest tests/test_xml_writer.py -v`

Expected: FAIL with missing `XmlDocumentWriter`.

- [ ] **Step 3: 원시/의미 XML 작성기 구현**

`XmlDocumentWriter`는 `ElementTree`만 사용하며 문자열 연결로 XML을 만들지 않는다.

```python
class XmlDocumentWriter:
    def write_raw(self, document: TaggedDocument, path: Path) -> None: ...
    def write_semantic(
        self, document: TaggedDocument, path: Path
    ) -> tuple[dict[str, object], ...]: ...
```

원시 XML 요소 규격:

```xml
<tagged-document source="..." marked="true" language="en">
  <element source-role="H2" semantic-role="heading" object-ref="81 0 R">
    <fragment page-index="0" mcid="8"><part>Settings &gt; General</part></fragment>
  </element>
</tagged-document>
```

의미 XML은 `semantic_role`을 요소명으로 사용하고, `unknown`에는
`source-role` 속성을 반드시 기록한다. `heading`에는 알려진 경우 `level`을
기록한다. 각 직접 `ContentFragment`는 `<text page-index="..." mcid="...">`로
기록하고 `join_text_parts` 결과를 넣는다. 쓰기 직후 XML을 다시 파싱하여
well-formed 여부와 `itertext()` 텍스트가 쓰기 전 의미 텍스트와 같은지 검증한다.

- [ ] **Step 4: XML 테스트 통과 확인**

Run: `.venv\Scripts\python -m pytest tests/test_xml_writer.py tests/test_text_joining.py -v`

Expected: 모든 테스트 PASS.

- [ ] **Step 5: XML 작성기 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/xml_writer.py samples/tagged_pdf_xml_poc/tests/test_xml_writer.py
git commit -m "Serialize tagged structure to auditable XML"
```

### Task 7: 기준 텍스트와 품질 평가

**Files:**
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pymupdf_baseline.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/evaluate_quality.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_quality_evaluator.py`

- [ ] **Step 1: 하드 게이트와 측정 지표 실패 테스트 작성**

```python
from pathlib import Path
from tagged_pdf_extractor.application.evaluate_quality import QualityEvaluator
from tagged_pdf_extractor.domain.models import ContentFragment, StructureElement, TaggedDocument


def test_quality_report_counts_headings_unknowns_and_special_chars() -> None:
    text = "Settings > General → Accessibility"
    document = TaggedDocument(
        Path("manual.pdf"), True, "en", (),
        (
            StructureElement("H1", "heading", 1, children=(ContentFragment(0, 1, ("Accessibility",)),)),
            StructureElement("P", "paragraph", children=(ContentFragment(0, 2, (text,)),)),
        ),
    )
    report = QualityEvaluator().evaluate(
        document,
        baseline_text="Accessibility Settings > General → Accessibility",
        xml_round_trip_ok=True,
    )
    assert report.metrics["heading_count"] == 1
    assert report.metrics["special_characters"][">"]["tagged"] == 1
    assert report.metrics["character_match_ratio"] == 1.0
    assert report.status == "pass"


def test_missing_body_fails_hard_gate() -> None:
    document = TaggedDocument(Path("manual.pdf"), True, "en", (), ())
    report = QualityEvaluator().evaluate(document, baseline_text="body", xml_round_trip_ok=True)
    assert report.hard_gates["has_body"] is False
    assert report.status == "fail"
```

- [ ] **Step 2: 품질 평가 테스트 실패 확인**

Run: `.venv\Scripts\python -m pytest tests/test_quality_evaluator.py -v`

Expected: FAIL with missing evaluator.

- [ ] **Step 3: 기준 추출기와 평가기 구현**

```python
# infrastructure/pymupdf_baseline.py
from pathlib import Path
import fitz


class PyMuPdfBaselineReader:
    def read_text(self, pdf_path: Path) -> str:
        with fitz.open(pdf_path) as document:
            return "\n".join(page.get_text("text") for page in document)
```

`QualityEvaluator`는 트리를 재귀 순회하여 직접 조각을 한 번씩만 수집한다.
비교용 텍스트만 NFC 정규화와 연속 공백 축약을 적용한다. 원본 XML 텍스트는
변경하지 않는다. `_collect_text`는 비어 있지 않은 조각을 논리 순서로 모아
단일 공백으로 연결한다.

```python
def evaluate(
    self, document: TaggedDocument, baseline_text: str,
    xml_round_trip_ok: bool, join_decisions: tuple[dict[str, object], ...] = (),
) -> QualityReport:
    tagged_text = self._collect_text(document.children)
    normalized_tagged = self._normalize_for_measurement(tagged_text)
    normalized_baseline = self._normalize_for_measurement(baseline_text)
    matched = sum(
        block.size for block in SequenceMatcher(
            None, normalized_baseline, normalized_tagged, autojunk=False
        ).get_matching_blocks()
    )
    ratio = matched / len(normalized_baseline) if normalized_baseline else 1.0
```

`metrics`에는 `element_count`, `fragment_count`, `heading_count`, `body_count`,
`unknown_role_count`, `empty_element_count`, `unresolved_mcid_count`,
`character_match_ratio`, `tagged_character_count`, `baseline_character_count`,
`special_characters`를 기록한다. 특수문자 집합은 `>→/&:[]()`이다.

하드 게이트는 `is_marked`, `has_structure`, `has_heading`, `has_body`,
`xml_round_trip`, `resolved_references_reported`로 고정하고 모두 참일 때만
`status="pass"`를 반환한다. `unresolved_mcid`가 있어도 누락 개수와 위치가
진단에 기록되면 `resolved_references_reported`는 참이다.

평가기 자체가 각 `ContentFragment`에 `join_text_parts`를 적용해 모든 공백 변경
판단을 `QualityReport.join_decisions`에 기록한다. XML 작성기도 같은 함수를
사용하므로 의미 XML과 품질 리포트의 텍스트 연결 규칙이 달라지지 않는다.

- [ ] **Step 4: 품질 테스트 통과 확인**

Run: `.venv\Scripts\python -m pytest tests/test_quality_evaluator.py -v`

Expected: `2 passed`.

- [ ] **Step 5: 품질 평가 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/evaluate_quality.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/pymupdf_baseline.py samples/tagged_pdf_xml_poc/tests/test_quality_evaluator.py
git commit -m "Measure tagged extraction quality"
```

### Task 8: Application 유스케이스와 안전한 출력 묶음

**Files:**
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application/extract_document.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/json_report_writer.py`
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/output_bundle.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_output_bundle.py`

- [ ] **Step 1: 출력 충돌과 세 산출물 생성 실패 테스트 작성**

```python
from pathlib import Path
import pytest
from tagged_pdf_extractor.domain.models import QualityReport, TaggedDocument
from tagged_pdf_extractor.infrastructure.output_bundle import OutputBundleWriter, OutputCollisionError


def test_refuses_existing_output_without_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "result"
    output.mkdir()
    (output / "raw_structure.xml").write_text("old", encoding="utf-8")
    document = TaggedDocument(tmp_path / "a.pdf", True, "en", (), ())
    report = QualityReport("fail", {}, {}, ())
    with pytest.raises(OutputCollisionError):
        OutputBundleWriter().write(document, report, output, overwrite=False)


def test_writes_required_artifacts(tmp_path: Path) -> None:
    document = TaggedDocument(tmp_path / "a.pdf", True, "en", (), ())
    report = QualityReport("fail", {}, {}, ())
    artifacts = OutputBundleWriter().write(document, report, tmp_path / "result")
    assert {p.name for p in (artifacts.raw_xml, artifacts.semantic_xml, artifacts.report_json)} == {
        "raw_structure.xml", "semantic_document.xml", "extraction_report.json"
    }
```

- [ ] **Step 2: 출력 테스트 실패 확인**

Run: `.venv\Scripts\python -m pytest tests/test_output_bundle.py -v`

Expected: FAIL with missing bundle writer.

- [ ] **Step 3: JSON 작성기, 묶음 작성기, 유스케이스 구현**

`JsonReportWriter`는 `QualityReport`를 UTF-8, `ensure_ascii=False`, 들여쓰기 2칸으로
직렬화한다. `OutputBundleWriter`는 대상의 형제 디렉터리에
`.result.staging-<uuid>`를 만들고 두 XML과 JSON을 모두 작성·재파싱한 후에만
세 파일을 대상 디렉터리로 옮긴다. 실패 시 staging 디렉터리만 삭제한다.

```python
class ExtractDocument:
    def __init__(self, reader, baseline_reader, evaluator, writer) -> None:
        self.reader = reader
        self.baseline_reader = baseline_reader
        self.evaluator = evaluator
        self.writer = writer

    def run(self, pdf_path: Path, output_dir: Path, overwrite: bool = False):
        document = self.reader.read(pdf_path)
        baseline = self.baseline_reader.read_text(pdf_path)
        provisional = self.evaluator.evaluate(document, baseline, xml_round_trip_ok=True)
        artifacts = self.writer.write(document, provisional, output_dir, overwrite)
        return document, provisional, artifacts
```

`OutputBundleWriter`가 XML 왕복 검사를 책임지며 실패하면 예외를 발생시키므로
Application은 성공적인 write에 대해서만 `xml_round_trip_ok=True`를 사용한다.

- [ ] **Step 4: 출력 및 전체 단위 테스트 통과 확인**

Run: `.venv\Scripts\python -m pytest tests -v --ignore=tests/test_zc_integration.py`

Expected: 모든 단위 테스트 PASS.

- [ ] **Step 5: Application과 출력 묶음 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/application samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/json_report_writer.py samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/infrastructure/output_bundle.py samples/tagged_pdf_xml_poc/tests/test_output_bundle.py
git commit -m "Add tagged extraction use case and outputs"
```

### Task 9: CLI, 실제 PDF 통합 테스트, 사용 문서

**Files:**
- Create: `samples/tagged_pdf_xml_poc/src/tagged_pdf_extractor/cli.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_cli.py`
- Create: `samples/tagged_pdf_xml_poc/tests/test_zc_integration.py`
- Create: `samples/tagged_pdf_xml_poc/README.md`
- Generate: `samples/tagged_pdf_xml_poc/outputs/BN68-25100B-00/raw_structure.xml`
- Generate: `samples/tagged_pdf_xml_poc/outputs/BN68-25100B-00/semantic_document.xml`
- Generate: `samples/tagged_pdf_xml_poc/outputs/BN68-25100B-00/extraction_report.json`

- [ ] **Step 1: CLI와 실제 샘플 통합 실패 테스트 작성**

```python
# tests/test_cli.py
from tagged_pdf_extractor.cli import build_parser


def test_cli_requires_pdf_and_output_paths() -> None:
    args = build_parser().parse_args(["manual.pdf", "--output", "out"])
    assert args.pdf.name == "manual.pdf"
    assert args.output.name == "out"
    assert args.overwrite is False
```

```python
# tests/test_zc_integration.py
from pathlib import Path
import pytest
from tagged_pdf_extractor.infrastructure.pypdf_reader import TaggedPdfReader

PDF = Path(__file__).parents[2] / "SUG_RAW" / "0_TV_ZC" / "BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf"


@pytest.mark.skipif(not PDF.exists(), reason="ZC tagged PDF sample is not available")
def test_zc_pdf_has_recoverable_tagged_hierarchy() -> None:
    document = TaggedPdfReader().read(PDF)
    assert document.marked is True
    assert document.children
```

- [ ] **Step 2: CLI와 통합 테스트 실패 확인**

Run: `.venv\Scripts\python -m pytest tests/test_cli.py tests/test_zc_integration.py -v`

Expected: CLI 테스트 FAIL. 통합 테스트는 구현 상태에 따라 PASS하거나 실제 태그
해석 결함을 구체적으로 드러낸다.

- [ ] **Step 3: CLI와 README 구현**

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract tagged PDF structure to XML")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    use_case = ExtractDocument(
        TaggedPdfReader(), PyMuPdfBaselineReader(),
        QualityEvaluator(), OutputBundleWriter(),
    )
    try:
        _, report, artifacts = use_case.run(args.pdf, args.output, args.overwrite)
    except (OSError, TaggedPdfError, OutputCollisionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(artifacts.report_json)
    return 0 if report.status == "pass" else 1
```

README에는 프로젝트 경계, Python 3.11 요구사항, 설치 명령, 정확한 ZC 실행 명령,
산출물 설명, 종료 코드 `0=hard gates pass`, `1=extraction completed but gate failed`,
`2=execution error`를 기록한다.

- [ ] **Step 4: 전체 테스트와 실제 추출 실행**

Run: `.venv\Scripts\python -m pytest tests -v`

Expected: 모든 테스트 PASS 또는 샘플 부재 시 통합 테스트 1개만 명시적으로 SKIP.

Run:

```powershell
.venv\Scripts\tagged-pdf-extract "C:\Users\bella\image-extractor\samples\SUG_RAW\0_TV_ZC\BN68-25100B-00_SUG_Y26 TV ALL_ZC_L02_260122.0.pdf" --output "outputs\BN68-25100B-00"
```

Expected: 세 산출물이 생성되고 종료 코드는 품질 하드 게이트 결과에 따라 `0` 또는
`1`이다. 종료 코드 `1`은 프로그램 실패가 아니라 실제 PDF 태그 품질의 POC 결과다.

검증 명령:

```powershell
.venv\Scripts\python -c "from xml.etree import ElementTree as ET; ET.parse(r'outputs\BN68-25100B-00\raw_structure.xml'); ET.parse(r'outputs\BN68-25100B-00\semantic_document.xml'); print('xml ok')"
.venv\Scripts\python -c "import json; from pathlib import Path; p=Path(r'outputs\BN68-25100B-00\extraction_report.json'); d=json.loads(p.read_text(encoding='utf-8')); print(d['status'], d['metrics'])"
```

Expected: `xml ok`와 JSON의 실제 status/metrics가 출력된다.

- [ ] **Step 5: CLI와 POC 결과 커밋**

```powershell
git add samples/tagged_pdf_xml_poc/pyproject.toml samples/tagged_pdf_xml_poc/README.md samples/tagged_pdf_xml_poc/src samples/tagged_pdf_xml_poc/tests
git commit -m "Run tagged PDF XML extraction POC"
```

생성된 `outputs/`는 크기와 민감도를 확인한 뒤 별도 커밋 여부를 결정한다. 코드
커밋에는 자동으로 포함하지 않는다.

## 최종 검증

- [ ] `.venv\Scripts\python -m pytest tests -v`에서 실패 0개 확인
- [ ] `.venv\Scripts\python -m compileall src tests` 성공 확인
- [ ] `raw_structure.xml`과 `semantic_document.xml` 왕복 파싱 성공 확인
- [ ] `extraction_report.json`에 헤딩 수, 본문 수, unknown role, unresolved MCID,
  커버리지, 특수문자 결과가 모두 존재하는지 확인
- [ ] 의미 XML에서 실제 OSD 경로와 문장 단절 사례를 사람이 직접 표본 검토
- [ ] 상위 프로젝트 `src/`, 체크리스트, Streamlit 파일의 변경이 없는지
  `git diff -- samples/tagged_pdf_xml_poc` 범위와 전체 `git status`로 확인
