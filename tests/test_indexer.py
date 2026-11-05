from types import SimpleNamespace

import src.vector_db.indexer as indexer


class FakeClient:
	def __init__(self, points):
		self.points = points
		self.query_limit = None
		self.closed = False

	def collection_exists(self, _collection_name):
		return True

	def query_points(self, **kwargs):
		self.query_limit = kwargs["limit"]
		return SimpleNamespace(points=self.points)

	def close(self):
		self.closed = True


def point(score, source):
	return SimpleNamespace(
		score=score,
		payload={"source": source, "text": f"chunk from {source}"},
	)


def test_search_chunks_returns_best_match_per_source(monkeypatch) -> None:
	client = FakeClient(
		[
			point(0.99, "guideline-a.pdf"),
			point(0.97, "guideline-a.pdf"),
			point(0.95, "guideline-b.pdf"),
			point(0.93, "guideline-c.pdf"),
		]
	)
	monkeypatch.setattr(indexer, "embed_texts", lambda _texts: [[0.1, 0.2]])

	results = indexer.search_chunks("query", limit=3, client=client)

	assert [result["payload"]["source"] for result in results] == [
		"guideline-a.pdf",
		"guideline-b.pdf",
		"guideline-c.pdf",
	]
	assert [result["score"] for result in results] == [0.99, 0.95, 0.93]
	assert client.query_limit == 15
	assert not client.closed


def test_search_chunks_normalizes_source_path_case_and_slashes(monkeypatch) -> None:
	client = FakeClient(
		[
			point(0.99, r"C:\Guidelines\Guide.pdf"),
			point(0.97, "c:/guidelines/guide.pdf"),
			point(0.95, r"C:\Guidelines\Other.pdf"),
		]
	)
	monkeypatch.setattr(indexer, "embed_texts", lambda _texts: [[0.1]])

	results = indexer.search_chunks("query", limit=2, client=client)

	assert [result["payload"]["source"] for result in results] == [
		r"C:\Guidelines\Guide.pdf",
		r"C:\Guidelines\Other.pdf",
	]


def test_search_chunks_rejects_non_positive_limit() -> None:
	try:
		indexer.search_chunks("query", limit=0, client=FakeClient([]))
	except ValueError as exc:
		assert "positive" in str(exc)
	else:
		raise AssertionError("Expected a non-positive limit to be rejected.")
