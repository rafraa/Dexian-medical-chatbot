#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from src.vector_db.indexer import index_file

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".nxml", ".xml", ".html", ".htm"}


def iter_supported_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Index all supported text-based documents into the local Qdrant vector store."
    )
    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing the documents to ingest",
    )
    parser.add_argument(
        "--jurisdiction",
        required=True,
        choices=["EG", "EU", "US"],
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit for testing. Use 0 to process all files.",
    )
    args = parser.parse_args()

    root = args.folder
    if not root.exists():
        raise FileNotFoundError(f"Folder does not exist: {root}")

    files = list(iter_supported_files(root))
    if args.limit > 0:
        files = files[: args.limit]

    if not files:
        print(f"No supported files found under {root}.")
        return

    total = 0
    for path in files:
        try:
            count = index_file(str(path), args.jurisdiction)
            total += count
            print(f"Indexed {count} chunks from {path}")
        except Exception as exc:  # pragma: no cover - CLI robustness
            print(f"Failed to index {path}: {exc}")

    print(f"Finished. Indexed {total} total chunks across {len(files)} files.")


if __name__ == "__main__":
    main()
