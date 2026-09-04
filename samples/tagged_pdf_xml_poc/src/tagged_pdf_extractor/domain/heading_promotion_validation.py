from __future__ import annotations

from collections.abc import Iterable

from tagged_pdf_extractor.domain.models import (
    ContentFragment,
    HeadingPromotion,
    StructureElement,
)


class HeadingPromotionTracker:
    """Validate promotion paths while a consumer performs its normal traversal."""

    def __init__(self, promotions: Iterable[HeadingPromotion]) -> None:
        self._promotion_by_path: dict[tuple[int, ...], HeadingPromotion] = {}
        for promotion in promotions:
            if promotion.child_path in self._promotion_by_path:
                raise ValueError(
                    f"duplicate heading promotion path {promotion.child_path}"
                )
            self._promotion_by_path[promotion.child_path] = promotion
        self._applied_paths: set[tuple[int, ...]] = set()

    def apply(
        self,
        child_path: tuple[int, ...],
        child: StructureElement | ContentFragment,
    ) -> HeadingPromotion | None:
        promotion = self._promotion_by_path.get(child_path)
        if promotion is None:
            return None
        if (
            not isinstance(child, StructureElement)
            or child.semantic_role != "list_item"
        ):
            raise ValueError(
                "heading promotion path "
                f"{child_path} must target a list_item StructureElement"
            )
        self._applied_paths.add(child_path)
        return promotion

    def assert_all_applied(self) -> None:
        unresolved = tuple(
            path
            for path in self._promotion_by_path
            if path not in self._applied_paths
        )
        if unresolved:
            raise ValueError(f"unresolved heading promotion path {unresolved[0]}")

    @property
    def applied_count(self) -> int:
        return len(self._applied_paths)
