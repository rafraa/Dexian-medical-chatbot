from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http import models

from config.settings import CHUNK_OVERLAP, CHUNK_SIZE, QDRANT_COLLECTION
from src.ingestion.chunker import chunk_text
from src.ingestion.embedder import embed_texts
from src.ingestion.parser import extract_document_pages
from src.vector_db.qdrant_client import ensure_collection, get_qdrant_client

RETRIEVAL_CANDIDATE_MULTIPLIER = 5


def index_file(
	file_path: str,
	jurisdiction: str,
	client: QdrantClient | None = None,
) -> int:
	"""Extract, chunk, embed, and index a supported document format."""
	owns_client = client is None
	client = client or get_qdrant_client()
	try:
		documents: list[dict[str, str | int]] = []
		for page in extract_document_pages(file_path):
			for chunk_index, text in enumerate(
				chunk_text(str(page["text"]), CHUNK_SIZE, CHUNK_OVERLAP)
			):
				documents.append(
					{
						"text": text,
						"source": page["source"],
						"page": page["page"],
						"chunk_index": chunk_index,
						"jurisdiction": jurisdiction.upper(),
						**{
							key: value
							for key, value in page.items()
							if key not in {"text", "source", "page"}
						},
					}
				)
		if not documents:
			return 0

		ensure_collection(client)
		vectors = embed_texts([str(document["text"]) for document in documents])
		points = [
			models.PointStruct(
				id=str(
					uuid5(
						NAMESPACE_URL,
						f"{document['source']}:{document['page']}:{document['chunk_index']}",
					)
				),
				vector=vector,
				payload=document,
			)
			for document, vector in zip(documents, vectors, strict=True)
		]
		client.upsert(collection_name=QDRANT_COLLECTION, points=points, wait=True)
		return len(points)
	finally:
		if owns_client:
			client.close()


def search_chunks(
	query: str,
	limit: int = 5,
	jurisdiction: str | None = None,
	client: QdrantClient | None = None,
) -> list[dict[str, object]]:
	"""Return the closest chunks, preferring one result per source document."""
	if limit <= 0:
		raise ValueError("limit must be positive.")
	owns_client = client is None
	client = client if client is not None else get_qdrant_client()
	try:
		if not client.collection_exists(QDRANT_COLLECTION):
			return []
		query_filter = None
		if jurisdiction:
			query_filter = models.Filter(
				must=[
					models.FieldCondition(
						key="jurisdiction",
						match=models.MatchValue(value=jurisdiction.upper()),
					)
				]
			)
		response = client.query_points(
			collection_name=QDRANT_COLLECTION,
			query=embed_texts([query])[0],
			query_filter=query_filter,
			limit=limit * RETRIEVAL_CANDIDATE_MULTIPLIER,
			with_payload=True,
		)
		results: list[dict[str, object]] = []
		seen_sources: set[str] = set()
		for index, point in enumerate(response.points):
			payload = point.payload or {}
			source = payload.get("source")
			source_key = (
				str(source).replace("/", "\\").casefold()
				if isinstance(source, str) and source.strip()
				else f"__missing_source_{index}"
			)
			if source_key in seen_sources:
				continue
			seen_sources.add(source_key)
			results.append({"score": point.score, "payload": payload})
			if len(results) == limit:
				break
		return results
	finally:
		if owns_client:
			client.close()
