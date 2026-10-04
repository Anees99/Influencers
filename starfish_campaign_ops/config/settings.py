"""Central configuration for Starfish Campaign Operations Automation.

Everything is env-driven; nothing hardcodes credentials. Demo mode works
with zero configuration. AI (Qwen-compatible) mode is strictly optional and
is NEVER used for financial/numeric reconciliation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv missing
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
DEMO_DATA_DIR = BASE_DIR / "demo_data"
OUTPUTS_DIR = BASE_DIR / "outputs"
DB_PATH = Path(os.getenv("STARFISH_DB", str(BASE_DIR / "starfish.db")))


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # ---- modes -------------------------------------------------------
    mode: str = os.getenv("STARFISH_MODE", "demo")            # demo | ai
    qwen_mode: str = os.getenv("QWEN_MODE", "")               # "" | ollama | openai | gemini | groq

    # ---- Qwen / OpenAI-compatible endpoint ---------------------------
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    qwen_model: str = os.getenv("QWEN_MODEL", "qwen3-coder")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""), repr=False)

    # ---- Google Gemini (OpenAI-compatible endpoint) -------------------
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""), repr=False)
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # ---- Groq (OpenAI-compatible endpoint) ----------------------------
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""), repr=False)
    groq_model: str = os.getenv("GROQ_MODEL", "gpt-oss-120b")

    # ---- matching thresholds (deterministic) -------------------------
    auto_accept: float = _f("MATCH_AUTO_ACCEPT", 0.85)
    review_min: float = _f("MATCH_REVIEW_MIN", 0.55)

    # ---- financial tolerance ------------------------------------------
    amount_tol_abs: float = _f("AMOUNT_TOL_ABS", 0.01)   # cents-level exactness
    amount_tol_pct: float = _f("AMOUNT_TOL_PCT", 0.0)

    # ---- screenshot extraction ----------------------------------------
    screenshot_confidence_min: float = _f("SCREENSHOT_CONFIDENCE_MIN", 0.85)

    outputs_dir: Path = OUTPUTS_DIR
    demo_data_dir: Path = DEMO_DATA_DIR
    db_path: Path = DB_PATH

    @property
    def ai_enabled(self) -> bool:
        if self.mode != "ai":
            return False
        if self.qwen_mode == "ollama":
            return True
        if self.qwen_mode == "openai":
            return bool(self.openai_base_url)
        if self.qwen_mode == "gemini":
            return bool(self.gemini_api_key)
        if self.qwen_mode == "groq":
            return bool(self.groq_api_key)
        return False


settings = Settings()
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
