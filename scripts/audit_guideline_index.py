import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import QDRANT_COLLECTION
from src.vector_db.qdrant_client import get_qdrant_client

SCROLL_PAGE_SIZE = 1000


def audit_index(client: Any | None = None) -> dict[str, Any]:
	"""Summarize indexed document provenance without reading chunk text or vectors."""
	owns_client = client is None
	client = client if client is not None else get_qdrant_client()
	try:
		if not client.collection_exists(QDRANT_COLLECTION):
			raise RuntimeError(f"Qdrant collection {QDRANT_COLLECTION!r} does not exist.")

		chunks_by_source: Counter[str] = Counter()
		pages_by_source: dict[str, set[int]] = defaultdict(set)
		jurisdictions_by_source: dict[str, set[str]] = defaultdict(set)
		metadata_by_source: dict[str, dict[str, str]] = defaultdict(dict)
		jurisdiction_chunks: Counter[str] = Counter()
		missing_source_chunks = 0
		missing_jurisdiction_chunks = 0
		total_chunks = 0
		offset: Any | None = None

		while True:
			records, next_offset = client.scroll(
				collection_name=QDRANT_COLLECTION,
				limit=SCROLL_PAGE_SIZE,
				offset=offset,
				with_payload=[
					"source",
					"jurisdiction",
					"page",
					"source_type",
					"guideline_status",
					"title",
					"book_title",
					"journal",
					"article_type",
					"publisher",
					"author",
					"publication_year",
					"doi",
					"license",
					"license_url",
					"document_type",
				],
				with_vectors=False,
			)
			for record in records:
				total_chunks += 1
				payload = record.payload or {}
				source = payload.get("source")
				jurisdiction = payload.get("jurisdiction")
				page = payload.get("page")
				if isinstance(source, str) and source.strip():
					chunks_by_source[source] += 1
					if type(page) is int:
						pages_by_source[source].add(page)
					if isinstance(jurisdiction, str) and jurisdiction.strip():
						jurisdictions_by_source[source].add(jurisdiction.upper())
				else:
					missing_source_chunks += 1
				if isinstance(jurisdiction, str) and jurisdiction.strip():
					jurisdiction_chunks[jurisdiction.upper()] += 1
				else:
					missing_jurisdiction_chunks += 1
				for field in METADATA_FIELDS:
					value = payload.get(field)
					if isinstance(value, str) and value.strip():
						source_key = (
							source
							if isinstance(source, str) and source.strip()
							else f"__missing_source_{total_chunks}"
						)
						if field not in metadata_by_source[source_key]:
							metadata_by_source[source_key][field] = value.strip()
			if next_offset is None:
				break
			if next_offset == offset:
				raise RuntimeError("Qdrant returned a repeated scroll offset.")
			offset = next_offset

		return {
			"collection": QDRANT_COLLECTION,
			"total_chunks": total_chunks,
			"unique_sources": len(chunks_by_source),
			"jurisdiction_chunks": dict(sorted(jurisdiction_chunks.items())),
			"missing_source_chunks": missing_source_chunks,
			"missing_jurisdiction_chunks": missing_jurisdiction_chunks,
			"metadata_source_counts": dict(
				sorted(metadata_field_source_counts(metadata_by_source).items())
			),
			"sources": [
				{
					"source": source,
					"chunks": chunks,
					"pages": len(pages_by_source[source]),
					"jurisdictions": sorted(jurisdictions_by_source[source]),
					**metadata_by_source.get(source, {}),
				}
				for source, chunks in chunks_by_source.most_common()
			],
		}
	finally:
		if owns_client:
			client.close()


METADATA_FIELDS = (
	"source_type",
	"guideline_status",
	"title",
	"book_title",
	"journal",
	"article_type",
	"publisher",
	"author",
	"publication_year",
	"doi",
	"license",
	"license_url",
	"document_type",
)


def metadata_field_source_counts(
	metadata_by_source: dict[str, dict[str, str]],
) -> Counter[str]:
	return Counter(
		field
		for metadata in metadata_by_source.values()
		for field in metadata
	)


def _format_source(source: dict[str, Any]) -> str:
	title = source.get("title", source["source"])
	if source.get("book_title"):
		title = f"{title} — {source['book_title']}"
	details = [
		f"`{source['source']}`",
		f"{source['chunks']} chunks",
		f"{source['pages']} pages",
		f"jurisdiction(s): {', '.join(source['jurisdictions']) or 'unknown'}",
	]
	for field, label in (
		("source_type", "source type"),
		("guideline_status", "guideline status"),
		("document_type", "type"),
		("article_type", "article type"),
		("journal", "journal"),
		("publisher", "publisher"),
		("author", "author"),
		("publication_year", "year"),
		("doi", "DOI"),
		("license", "license"),
	):
		if source.get(field):
			details.append(f"{label}: {source[field]}")
	return f"- **{title}** — " + "; ".join(details)


def format_report(audit: dict[str, Any], top_sources: int) -> str:
	lines = [
		"# Medical-reference index audit",
		"",
		f"- **Collection:** `{audit['collection']}`",
		f"- **Indexed chunks:** {audit['total_chunks']}",
		f"- **Unique source documents:** {audit['unique_sources']}",
		f"- **Chunks missing source metadata:** {audit['missing_source_chunks']}",
		f"- **Chunks missing jurisdiction metadata:** {audit['missing_jurisdiction_chunks']}",
		"",
		"## Jurisdiction distribution",
		"",
	]
	if audit["jurisdiction_chunks"]:
		lines.extend(
			f"- **{jurisdiction}:** {count} chunks"
			for jurisdiction, count in audit["jurisdiction_chunks"].items()
		)
	else:
		lines.append("- No jurisdiction metadata found.")
	lines.extend(["", f"## Sources with most chunks (top {top_sources})", ""])
	if audit["sources"]:
		lines.extend(
			_format_source(source)
			for source in audit["sources"][:top_sources]
		)
	else:
		lines.append("- No source documents found.")
	if audit.get("metadata_source_counts"):
		lines.extend(["", "## Metadata coverage", ""])
		lines.extend(
			f"- **{field}:** {count} source documents"
			for field, count in audit["metadata_source_counts"].items()
		)
	lines.extend(
		[
			"",
			"## Metadata limitations",
			"",
			"Source type and guideline status are metadata classifications, not "
			"independent verification. Bibliographic fields are shown when available. "
			"Confirm source authority, currency, and licensing against the publisher.",
		]
	)
	return "\n".join(lines) + "\n"


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Audit indexed document and jurisdiction metadata without printing medical text."
	)
	parser.add_argument(
		"--output",
		type=Path,
		help="Optional Markdown report path; otherwise print the report.",
	)
	parser.add_argument("--top-sources", type=int, default=30)
	args = parser.parse_args()
	if args.top_sources <= 0:
		parser.error("--top-sources must be positive.")

	report = format_report(audit_index(), args.top_sources)
	if args.output:
		args.output.parent.mkdir(parents=True, exist_ok=True)
		args.output.write_text(report, encoding="utf-8")
		print(f"Index audit saved to {args.output}")
	else:
		print(report)


if __name__ == "__main__":
	main()
