"""Project stage transitions. Orchestrator owns the machine; LLM does not."""

from __future__ import annotations

from backend.domain.enums import ProjectStage

ALLOWED_TRANSITIONS: dict[ProjectStage, set[ProjectStage]] = {
    ProjectStage.CREATED: {ProjectStage.INGESTING, ProjectStage.FAILED},
    ProjectStage.INGESTING: {
        ProjectStage.ANALYZING,
        ProjectStage.PAUSED,
        ProjectStage.FAILED,
    },
    ProjectStage.ANALYZING: {
        ProjectStage.PLANNING,
        ProjectStage.PAUSED,
        ProjectStage.FAILED,
    },
    ProjectStage.PLANNING: {
        ProjectStage.WAITING_FOR_OUTLINE_APPROVAL,
        ProjectStage.PAUSED,
        ProjectStage.FAILED,
    },
    ProjectStage.WAITING_FOR_OUTLINE_APPROVAL: {
        ProjectStage.PRODUCING,
        ProjectStage.PLANNING,
        ProjectStage.PAUSED,
        ProjectStage.FAILED,
    },
    ProjectStage.PRODUCING: {
        ProjectStage.REVIEWING,
        ProjectStage.PAUSED,
        ProjectStage.FAILED,
    },
    ProjectStage.REVIEWING: {
        ProjectStage.REVISING,
        ProjectStage.FINALIZING,
        ProjectStage.PRODUCING,
        ProjectStage.PAUSED,
        ProjectStage.FAILED,
    },
    ProjectStage.REVISING: {
        ProjectStage.REVIEWING,
        ProjectStage.PAUSED,
        ProjectStage.FAILED,
    },
    ProjectStage.FINALIZING: {
        ProjectStage.READY_FOR_EXPORT,
        ProjectStage.PAUSED,
        ProjectStage.FAILED,
    },
    ProjectStage.READY_FOR_EXPORT: {
        ProjectStage.EXPORTED,
        ProjectStage.PRODUCING,
        ProjectStage.INGESTING,
        ProjectStage.PAUSED,
        ProjectStage.FAILED,
    },
    ProjectStage.EXPORTED: {
        ProjectStage.INGESTING,
        ProjectStage.ANALYZING,
        ProjectStage.PRODUCING,
    },
    ProjectStage.PAUSED: {
        ProjectStage.INGESTING,
        ProjectStage.ANALYZING,
        ProjectStage.PLANNING,
        ProjectStage.WAITING_FOR_OUTLINE_APPROVAL,
        ProjectStage.PRODUCING,
        ProjectStage.REVIEWING,
        ProjectStage.REVISING,
        ProjectStage.FINALIZING,
        ProjectStage.READY_FOR_EXPORT,
        ProjectStage.FAILED,
    },
    ProjectStage.FAILED: {
        ProjectStage.INGESTING,
        ProjectStage.ANALYZING,
        ProjectStage.PLANNING,
        ProjectStage.PRODUCING,
    },
}


def can_transition(current: ProjectStage, target: ProjectStage) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def assert_transition(current: ProjectStage, target: ProjectStage) -> None:
    if not can_transition(current, target):
        raise ValueError(f"Illegal stage transition: {current} → {target}")
