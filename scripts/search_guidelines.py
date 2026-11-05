import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from src.vector_db.indexer import search_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Search indexed guideline chunks.")
    parser.add_argument("query", help="Question in English or Arabic")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    for result in search_chunks(args.query, args.limit):
        payload = result["payload"]
        print(
            f"Score: {result['score']:.3f} | "
            f"{payload.get('title', payload.get('source'))} | "
            f"{payload.get('source')} | page {payload.get('page')} | "
            f"{payload.get('source_type', 'unknown')} | "
            f"guideline status: {payload.get('guideline_status', 'not_verified')}"
        )
        print(payload.get("text", ""))
        print()


if __name__ == "__main__":
    main()