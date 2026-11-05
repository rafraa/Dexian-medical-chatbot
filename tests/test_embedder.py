import json
from io import BytesIO

import src.ingestion.embedder as embedder


def test_embed_texts_keeps_embedding_model_alive(monkeypatch) -> None:
	requests = []
	response = BytesIO(
		json.dumps({"embeddings": [[0.1] * embedder.EMBEDDING_DIMENSION]}).encode()
	)
	monkeypatch.setattr(
		embedder,
		"urlopen",
		lambda request, timeout: requests.append((request, timeout)) or response,
	)

	vectors = embedder.embed_texts(["A query"])

	request, timeout = requests[0]
	body = json.loads(request.data.decode())
	assert len(vectors) == 1
	assert len(vectors[0]) == embedder.EMBEDDING_DIMENSION
	assert request.full_url.endswith("/api/embed")
	assert timeout == 120
	assert body["keep_alive"] == embedder.OLLAMA_KEEP_ALIVE
