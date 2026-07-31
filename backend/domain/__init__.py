"""Domain package exports."""

from backend.domain.edition import Claim, ReportEdition, SectionImpact
from backend.domain.enums import (
    ClaimRelation,
    EditionStatus,
    EvidenceType,
    ImpactDecision,
    IssueSeverity,
    MetricDirection,
    PageType,
    ProjectStage,
    ReviewDecision,
    SourceRole,
    SourceStatus,
    VerificationStatus,
    VisualType,
)
from backend.domain.evidence import (
    ArchitectureFact,
    ContentBlock,
    EvidenceItem,
    EvidencePack,
    MetricFact,
    ProcessFact,
)
from backend.domain.project import CorpusSnapshot, Project, Source, SourcePage
from backend.domain.report_plan import (
    CorpusAnalysis,
    OutlineNode,
    QuantitativeFinding,
    ReportPlan,
)
from backend.domain.review import (
    EditorialReview,
    ReviewIssue,
    RevisionResult,
    TechnicalReview,
)
from backend.domain.section import Section, SectionVersion
from backend.domain.visual import VisualRequest

__all__ = [
    "ArchitectureFact",
    "Claim",
    "ClaimRelation",
    "ContentBlock",
    "CorpusAnalysis",
    "CorpusSnapshot",
    "EditorialReview",
    "EditionStatus",
    "EvidenceItem",
    "EvidencePack",
    "EvidenceType",
    "ImpactDecision",
    "IssueSeverity",
    "MetricDirection",
    "MetricFact",
    "OutlineNode",
    "QuantitativeFinding",
    "PageType",
    "ProcessFact",
    "Project",
    "ProjectStage",
    "ReportEdition",
    "ReportPlan",
    "ReviewDecision",
    "ReviewIssue",
    "RevisionResult",
    "Section",
    "SectionImpact",
    "SectionVersion",
    "Source",
    "SourcePage",
    "SourceRole",
    "SourceStatus",
    "TechnicalReview",
    "VerificationStatus",
    "VisualRequest",
    "VisualType",
]
