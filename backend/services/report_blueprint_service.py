"""Build chapter-oriented blueprint from approved outline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ChapterBlueprintUnit:
    chapter_id: str
    node_id: str
    title: str
    objective: str
    core_message: str
    questions_to_answer: list[str]
    subsection_node_ids: list[str]
    planned_visual_types: list[str]


class ReportBlueprintService:
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
                )
            )
        return out
