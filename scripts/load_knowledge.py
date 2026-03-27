"""
scripts/load_knowledge.py
--------------------------
Indexes text/markdown files from data/knowledge/{domain}/ into ChromaDB.

Run once after adding or updating documents:
    python scripts/load_knowledge.py

Or for a single domain:
    python scripts/load_knowledge.py --domain legal

The script is idempotent — re-running adds documents again, so clear
the vector store first if you want a clean re-index:
    rm -rf data/vector_db/{domain}
"""

import sys
import argparse
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.retriever import add_documents, collection_size
from utils.config import get_config
from utils.logger import get_logger

logger = get_logger("load_knowledge")

DOMAINS      = ["strategy", "marketing", "legal", "engineering", "finance"]
EXTENSIONS   = {".txt", ".md", ".rst"}


def load_domain(domain: str, knowledge_dir: Path) -> int:
    domain_dir = knowledge_dir / domain
    if not domain_dir.exists():
        logger.warning("Directory not found: %s — skipping.", domain_dir)
        return 0

    texts:     list[str] = []
    metadatas: list[dict] = []

    for file_path in sorted(domain_dir.iterdir()):
        if file_path.suffix.lower() not in EXTENSIONS:
            continue
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8").strip()
            if not content:
                logger.debug("Skipping empty file: %s", file_path.name)
                continue
            texts.append(content)
            metadatas.append({
                "domain":   domain,
                "source":   file_path.name,
                "filepath": str(file_path),
            })
            logger.info("  Queued: %s (%d chars)", file_path.name, len(content))
        except Exception as exc:
            logger.error("  Failed to read %s: %s", file_path, exc)

    if not texts:
        logger.info("No documents found for domain '%s'.", domain)
        return 0

    added = add_documents(domain, texts, metadatas)
    logger.info(
        "Domain '%s': indexed %d/%d documents. Collection size: %d",
        domain, added, len(texts), collection_size(domain)
    )
    return added


def main():
    parser = argparse.ArgumentParser(description="Load knowledge into vector stores.")
    parser.add_argument(
        "--domain",
        choices=DOMAINS + ["all"],
        default="all",
        help="Which domain to load (default: all)",
    )
    args = parser.parse_args()

    config        = get_config()
    knowledge_dir = Path(config["KNOWLEDGE_DIR"])
    logger.info("Knowledge base directory: %s", knowledge_dir.resolve())

    domains = DOMAINS if args.domain == "all" else [args.domain]
    total   = 0

    for domain in domains:
        logger.info("Loading domain: %s", domain)
        total += load_domain(domain, knowledge_dir)

    logger.info("Done. Total documents indexed: %d", total)


if __name__ == "__main__":
    main()