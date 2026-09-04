import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import Specifier
from packaging.utils import canonicalize_name

import tagged_pdf_extractor


PROJECT_ROOT = Path(__file__).parents[1]


def test_project_isolation_contract() -> None:
    assert (PROJECT_ROOT / "pyproject.toml").is_file()
    assert tagged_pdf_extractor.__version__ == "0.1.0"

    for source_file in (PROJECT_ROOT / "src").rglob("*.py"):
        source = source_file.read_text(encoding="utf-8")
        assert "from src" not in source
        assert "import src" not in source


def test_pypdf_dependency_is_pinned_to_validated_private_api_version() -> None:
    project = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    requirements = [
        Requirement(dependency)
        for dependency in project["project"]["dependencies"]
    ]
    pypdf_requirements = [
        requirement
        for requirement in requirements
        if canonicalize_name(requirement.name) == "pypdf"
    ]

    assert len(pypdf_requirements) == 1
    requirement = pypdf_requirements[0]
    assert not requirement.extras
    assert requirement.url is None
    assert requirement.marker is None
    assert set(requirement.specifier) == {Specifier("==6.16.2")}
