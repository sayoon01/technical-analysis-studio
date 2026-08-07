"""Canonical Context Building Owner for chapter writing.

Also transforms approved outline → chapter units for EvidencePack queries.
Does not own LLM writing, persistence, or review.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.chapter import (
    ChapterDraft,
    ChapterSummaryMemory,
    ChapterWritingContext,
    OutlineChapterRef,
    ReportMemory,
)
from backend.domain.evidence import EvidencePack


@dataclass(slots=True)
class ChapterBlueprintUnit:
    """Outline → production unit (EvidencePackService input helper)."""

    chapter_id: str
    node_id: str
    title: str
    objective: str
    core_message: str
    questions_to_answer: list[str]
    subsection_node_ids: list[str]
    planned_visual_types: list[str]
    expected_length: int = 0


class ReportBlueprintService:
    """Canonical Owner: Writing Context assembly (+ outline chapter units)."""

    def build_from_outline(self, *, outline_nodes: list[dict]) -> list[ChapterBlueprintUnit]:
        by_parent: dict[str, list[dict]] = {}
        top: list[dict] = []
        for n in outline_nodes:
            pid = n.get("parent_id")
            if pid:
                by_parent.setdefault(pid, []).append(n)
            elif int(n.get("level") or 1) == 1:
                top.append(n)

        top.sort(key=lambda n: int(n.get("order") or 0))
        for items in by_parent.values():
            items.sort(key=lambda n: int(n.get("order") or 0))

        out: list[ChapterBlueprintUnit] = []
        for idx, n in enumerate(top, start=1):
            node_id = str(n["node_id"])
            subs = by_parent.get(node_id, [])
            out.append(
                ChapterBlueprintUnit(
                    chapter_id=f"CH-{idx:02d}",
                    node_id=node_id,
                    title=str(n.get("title") or ""),
                    objective=str(n.get("objective") or ""),
                    core_message=str(n.get("objective") or ""),
                    questions_to_answer=list(n.get("analysis_questions") or []),
                    subsection_node_ids=[str(s["node_id"]) for s in subs],
                    planned_visual_types=list(n.get("planned_visuals") or []),
                    expected_length=int(n.get("expected_length") or 0),
                )
            )
        return out

    def outline_chapter_refs(
        self, chapter_units: list[ChapterBlueprintUnit]
    ) -> list[OutlineChapterRef]:
        return [
            OutlineChapterRef(
                node_id=u.node_id,
                title=u.title,
                objective=u.objective,
                analysis_questions=list(u.questions_to_answer),
                expected_length=u.expected_length,
                order=i,
            )
            for i, u in enumerate(chapter_units, start=1)
        ]

    def build_writing_context(
        self,
        *,
        plan: dict | None,
        chapter_units: list[ChapterBlueprintUnit],
        node: dict,
        chapter: ChapterBlueprintUnit | None,
        pack: EvidencePack,
        report_memory: ReportMemory,
        prev_summary: str | None = None,
        next_title: str | None = None,
        next_objective: str | None = None,
        format_notes: str | None = None,
        report_language: str = "ko",
    ) -> ChapterWritingContext:
        """Assemble report-level + continuity + current-chapter context for Writer."""
        plan_payload = (plan or {}).get("plan") if plan else None
        if not isinstance(plan_payload, dict):
            plan_payload = {}

        chapter_id = (
            chapter.chapter_id
            if chapter
            else f"CH-{node.get('node_id') or 'UNKNOWN'}"
        )
        questions = list(node.get("analysis_questions") or [])
        if chapter:
            questions = list(dict.fromkeys([*chapter.questions_to_answer, *questions]))

        target = int(node.get("expected_length") or 0)
        if chapter and chapter.expected_length:
            target = chapter.expected_length

        # Seed terminology from plan once into memory view (non-mutating copy)
        memory = report_memory.model_copy(deep=True)
        terms = plan_payload.get("terminology_policy") or {}
        if isinstance(terms, dict) and terms:
            for k, v in terms.items():
                label = f"{k}: {v}" if v else str(k)
                if label not in memory.established_terms:
                    memory.established_terms.append(label)

        return ChapterWritingContext(
            plan_title=(plan or {}).get("title") or plan_payload.get("title"),
            report_language=report_language,
            central_thesis=plan_payload.get("central_thesis")
            or (plan or {}).get("central_thesis"),
            purpose=(plan or {}).get("purpose") or plan_payload.get("purpose"),
            outline_chapters=self.outline_chapter_refs(chapter_units),
            report_memory=memory,
            prev_summary=prev_summary,
            chapter_id=chapter_id,
            title=str(node.get("title") or (chapter.title if chapter else "")),
            objective=str(
                node.get("objective")
                or (chapter.objective if chapter else "")
                or ""
            ),
            analysis_questions=questions,
            next_title=next_title,
            next_objective=next_objective,
            evidence_pack=pack,
            format_notes=format_notes,
            target_words=target,
        )

    def extend_report_memory(
        self,
        memory: ReportMemory,
        *,
        draft: ChapterDraft,
        summary: str,
    ) -> ReportMemory:
        """Update structured continuity after a chapter is finalized as draft."""
        updated = memory.model_copy(deep=True)
        updated.chapter_summaries.append(
            ChapterSummaryMemory(
                chapter_id=draft.chapter_id,
                title=draft.title,
                summary=(summary or "")[:400],
                key_takeaways=list(draft.key_takeaways[:5]),
            )
        )
        for t in draft.key_takeaways[:5]:
            if t and t not in updated.key_findings:
                updated.key_findings.append(t)
        for lim in draft.limitations[:3]:
            note = f"limitation:{lim}"
            if note not in updated.continuity_notes:
                updated.continuity_notes.append(note)
        # Cap growth so prompt context stays bounded
        updated.chapter_summaries = updated.chapter_summaries[-12:]
        updated.key_findings = updated.key_findings[-20:]
        updated.continuity_notes = updated.continuity_notes[-20:]
        updated.established_terms = updated.established_terms[:40]
        return updated
