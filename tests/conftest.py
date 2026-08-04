"""Global pytest defaults for deterministic local runs."""

from __future__ import annotations

import os


# Integration and unit tests must run without external Ollama services.
os.environ["TAS_LLM_MODE"] = "fake"
os.environ["TAS_EMBEDDING_MODE"] = "hash"
os.environ["TAS_LLM_STRICT"] = "1"

