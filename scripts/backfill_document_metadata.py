import argparse
import sys
from pathlib import Path
from typing import Any

from qdrant_client.http import models

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import QDRANT_COLLECTION
from src.ingestion.parser import extract_document_metadata
from src.vector_db.qdrant_client import get_qdrant_client

SCROLL_PAGE_SIZE = 1000


def backfill_metadata(apply_changes: bool = False, client: Any | None = None) -> dict[str, int]:
	"""Copy source-file metadata into existing Qdrant payloads without re-embedding."""
	owns_client = client is None
	client = client if client is not None else get_qdrant_client()
	try:
		if not client.collection_exists(QDRANT_COLLECTION):
			raise RuntimeError(f"Qdrant collection {QDRANT_COLLECTION!r} does not exist.")

		sources: set[str] = set()
		offset: Any | None = None
		while True:
			records, next_offset = client.scroll(
				collection_name=QDRANT_COLLECTION,
				limit=SCROLL_PAGE_SIZE,
				offset=offset,
				with_payload=["source"],
				with_vectors=False,
			)
			for record in records:
				source = (record.payload or {}).get("source")
				if isinstance(source, str) and source.strip():
					sources.add(source)
			if next_offset is None:
				break
			if next_offset == offset:
				raise RuntimeError("Qdrant returned a repeated scroll offset.")
			offset = next_offset

		updated = 0
		missing_files = 0
		for source in sorted(sources):
			path = Path(source)
			if not path.is_absolute():
				path = PROJECT_ROOT / path
			if not path.is_file():
				missing_files += 1
				print(f"Source file not found; skipped: {source}")
				continue
			metadata = extract_document_metadata(path)
			if apply_changes:
				client.set_payload(
					collection_name=QDRANT_COLLECTION,
					payload=metadata,
					points=models.Filter(
						must=[
							models.FieldCondition(
								key="source",
								match=models.MatchValue(value=source),
							)
						]
					),
					wait=True,
				)
			updated += 1
		return {
			"sources_found": len(sources),
			"sources_updated" if apply_changes else "sources_ready": updated,
			"missing_source_files": missing_files,
		}
	finally:
		if owns_client:
			client.close()


def main() -> None:
	parser = argparse.ArgumentParser(
		description=(
			"Extract metadata from indexed files and prepare a Qdrant payload backfill. "
			"Use --apply to write metadata; vectors are not recomputed."
		)
	)
	parser.add_argument(
		"--apply",
		action="store_true",
		help="write extracted metadata into existing Qdrant payloads",
	)
	args = parser.parse_args()
	result = backfill_metadata(apply_changes=args.apply)
	mode = "Applied" if args.apply else "Dry run: ready to update"
	print(f"{mode}: {result.get('sources_updated', result.get('sources_ready', 0))} sources.")
	print(f"Sources in index: {result['sources_found']}")
	print(f"Missing local source files: {result['missing_source_files']}")
	if not args.apply:
		print("Run again with --apply to update the existing index.")


if __name__ == "__main__":
	main()
