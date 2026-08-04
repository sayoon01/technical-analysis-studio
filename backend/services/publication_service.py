"""Build publication document from reviewed edition outputs."""

from __future__ import annotations

from backend.domain.publication import (
    ExecutiveSummary,
    PublicationChapter,
    PublicationDocument,
    PublicationFigure,
)


class PublicationService:
    def build_document(
        self,
        *,
        title: str,
        subtitle: str | None,
        sections: list[dict],
        visuals: dict,
    ) -> PublicationDocument:
        chapters = [
            PublicationChapter(
                chapter_id=s["section_id"],
                title=s.get("title") or s["section_id"],
                body_markdown=(s.get("content_markdown") or "").strip(),
            )
            for s in sections
        ]
        figures: list[PublicationFigure] = []
        for req in visuals.get("requests") or []:
            if req.get("visual_type") in {"BAR_CHART", "LINE_CHART", "PROCESS_FLOW", "ARCHITECTURE_DIAGRAM"}:
                figures.append(
                    PublicationFigure(
                        visual_id=req["visual_id"],
                        title=req.get("title") or req["visual_id"],
                        caption=req.get("purpose") or "",
                        source_pages=list(req.get("source_pages") or []),
                        asset_path=(visuals.get("rendered") or {}).get(req["visual_id"]),
                    )
                )
        return PublicationDocument(
            title=title,
            subtitle=subtitle,
            executive_summary=ExecutiveSummary(
                overview="본 문서는 업로드된 기술 자료의 핵심 근거를 기준으로 작성되었다.",
                highlights=[c.title for c in chapters[:3]],
            ),
            chapters=chapters,
            figures=figures,
            limitations=[],
            references=[],
        )
