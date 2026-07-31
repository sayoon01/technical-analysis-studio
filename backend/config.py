"""Application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    data_dir: Path = Path("./data")
    database_url: str = "sqlite:///./data/tas.db"
    vector_index_dir: Path = Path("./data/vector_indexes")
    pdf_render_dpi: int = 200
    ocr_enabled: bool = True
    max_revisions: int = 3
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:31b"
    ollama_timeout: float = 900.0
    embedding_model: str = "bge-m3"
    # llm | offline  — offline는 corpus 기반 deterministic (테스트/무LLM)
    llm_mode: str = "llm"
    # off | delta — evidence researcher never regenerates full EvidencePack JSON
    evidence_refine_mode: str = "off"


def load_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        data_dir=Path(os.getenv("DATA_DIR", "./data")),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/tas.db"),
        vector_index_dir=Path(os.getenv("VECTOR_INDEX_DIR", "./data/vector_indexes")),
        pdf_render_dpi=int(os.getenv("PDF_RENDER_DPI", "200")),
        ocr_enabled=os.getenv("OCR_ENABLED", "true").lower() in ("1", "true", "yes"),
        max_revisions=int(os.getenv("MAX_REVISIONS", "3")),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", os.getenv("GEMMA_MODEL", "gemma4:31b")),
        ollama_timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "900")),
        embedding_model=os.getenv(
            "EMBEDDING_MODEL", os.getenv("OLLAMA_EMBED_MODEL", "bge-m3")
        ),
        llm_mode=os.getenv("TAS_LLM_MODE", "llm").lower(),
        evidence_refine_mode=os.getenv("TAS_EVIDENCE_REFINE", "off").lower(),
    )


settings = load_settings()
