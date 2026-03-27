"""
utils/config.py
---------------
Loads .env and returns a validated config dict.
All infrastructure paths and optional API keys are declared here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_config: dict | None = None


def get_config() -> dict:
    global _config
    if _config is not None:
        return _config

    db_url    = os.getenv("DATABASE_URL",  "sqlite:///./data/venture.db")
    llm_model = os.getenv("LLM_MODEL",     "llama3.2:3b")
    llm_url   = os.getenv("LLM_BASE_URL",  "http://localhost:11434")
    log_level = os.getenv("LOG_LEVEL",     "INFO")
    log_file  = os.getenv("LOG_FILE",      "")

    # Web search — Tavily gives 1000 free searches/month, no card needed.
    # Sign up at https://tavily.com  → copy your API key here.
    # When empty, the system falls back to free DuckDuckGo HTML scraping.
    tavily_key = os.getenv("TAVILY_API_KEY", "")

    # Infrastructure paths (can be overridden in .env)
    artifact_dir  = os.getenv("ARTIFACT_DIR",  "./data/artifacts")
    vector_db_dir = os.getenv("VECTOR_DB_DIR", "./data/vector_db")
    knowledge_dir = os.getenv("KNOWLEDGE_DIR", "./data/knowledge")

    # Auto-create SQLite parent dir
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
        if db_path:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Auto-create all infrastructure dirs + domain knowledge sub-dirs
    for d in (artifact_dir, vector_db_dir, knowledge_dir):
        Path(d).mkdir(parents=True, exist_ok=True)
    for domain in ("strategy", "marketing", "legal", "engineering", "finance"):
        Path(knowledge_dir, domain).mkdir(parents=True, exist_ok=True)

    _config = {
        "DATABASE_URL":   db_url,
        "LLM_MODEL":      llm_model,
        "LLM_BASE_URL":   llm_url,
        "LOG_LEVEL":      log_level,
        "LOG_FILE":       log_file,
        "TAVILY_API_KEY": tavily_key,
        "ARTIFACT_DIR":   artifact_dir,
        "VECTOR_DB_DIR":  vector_db_dir,
        "KNOWLEDGE_DIR":  knowledge_dir,
    }
    return _config