"""
utils/retriever.py
------------------
Per-domain vector stores backed by ChromaDB with Ollama embeddings.

Fixes:
- Auto-detects embedding dimension mismatch and wipes stale collections.
- Uses langchain_chroma if available, falls back to community version.
- Separate embedding model (all-minilm:l6-v2) from the LLM model.
- Agents work fine with empty stores -- RAG is enhancement, not blocker.
"""

import shutil
import threading
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

from utils.config import get_config
from utils.logger import get_logger

logger = get_logger(__name__)

_stores: dict = {}
_lock   = threading.Lock()

VALID_DOMAINS = {"strategy", "marketing", "legal", "engineering", "finance"}

# Pull this model first: ollama pull all-minilm:l6-v2
# Smaller and faster than using the main LLM for embeddings.
# all-minilm:l6-v2 -> 384 dims
# If you prefer: nomic-embed-text -> 768 dims
EMBEDDING_MODEL = "all-minilm:l6-v2"


def _get_embeddings() -> OllamaEmbeddings:
    config = get_config()
    return OllamaEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=config["LLM_BASE_URL"],
    )


def _try_import_chroma():
    try:
        from langchain_chroma import Chroma
        return Chroma
    except ImportError:
        from langchain_community.vectorstores import Chroma
        return Chroma


def _get_store(domain: str):
    if domain in _stores:
        return _stores[domain]

    with _lock:
        if domain in _stores:
            return _stores[domain]

        config      = get_config()
        persist_dir = Path(config["VECTOR_DB_DIR"]) / domain
        persist_dir.mkdir(parents=True, exist_ok=True)
        Chroma = _try_import_chroma()

        try:
            store = Chroma(
                collection_name=f"{domain}_knowledge",
                embedding_function=_get_embeddings(),
                persist_directory=str(persist_dir),
            )
            # Dimension mismatch check
            try:
                count = store._collection.count()
                if count > 0:
                    store.similarity_search("test", k=1)
            except Exception as probe_err:
                if "dimension" in str(probe_err).lower():
                    logger.warning("Dimension mismatch in '%s' -- wiping stale collection.", domain)
                    del store
                    shutil.rmtree(str(persist_dir), ignore_errors=True)
                    persist_dir.mkdir(parents=True, exist_ok=True)
                    store = Chroma(
                        collection_name=f"{domain}_knowledge",
                        embedding_function=_get_embeddings(),
                        persist_directory=str(persist_dir),
                    )
                    logger.info("Recreated clean store for domain='%s'.", domain)
                else:
                    raise

            _stores[domain] = store
            logger.info("Chroma store ready for domain='%s' (model=%s)", domain, EMBEDDING_MODEL)

        except Exception as exc:
            logger.error("Failed to init Chroma for domain='%s': %s", domain, exc, exc_info=True)
            _stores[domain] = None

        return _stores[domain]


def get_retriever(domain: str, k: int = 4):
    if domain not in VALID_DOMAINS:
        logger.warning("get_retriever: unknown domain '%s'", domain)
        return None
    store = _get_store(domain)
    if store is None:
        return None
    return _SafeRetriever(store=store, k=k)


def add_documents(domain: str, texts: list[str],
                  metadatas: Optional[list[dict]] = None) -> int:
    if not texts:
        return 0
    store = _get_store(domain)
    if store is None:
        logger.error("add_documents: store for '%s' not available.", domain)
        return 0
    metas = metadatas or [{"domain": domain}] * len(texts)
    try:
        store.add_texts(texts=texts, metadatas=metas)
        logger.info("Indexed %d docs into domain='%s'", len(texts), domain)
        return len(texts)
    except Exception as exc:
        if "dimension" in str(exc).lower():
            logger.error(
                "Dimension mismatch for domain='%s'. "
                "Run: rmdir data\\vector_db  then re-run load_knowledge.py", domain
            )
        else:
            logger.error("add_documents failed for domain='%s': %s", domain, exc)
        return 0


def collection_size(domain: str) -> int:
    store = _get_store(domain)
    if store is None:
        return 0
    try:
        return store._collection.count()
    except Exception:
        return 0


class _SafeRetriever:
    def __init__(self, store, k: int):
        self._store = store
        self._k     = k

    def invoke(self, query: str) -> list[Document]:
        return self.get_relevant_documents(query)

    def get_relevant_documents(self, query: str) -> list[Document]:
        try:
            if self._store._collection.count() == 0:
                return []
            return self._store.similarity_search(query, k=self._k)
        except Exception as exc:
            logger.warning("RAG retrieval failed: %s", exc)
            return []