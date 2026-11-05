import json
from urllib.request import Request, urlopen

from config.settings import (
	EMBEDDING_DIMENSION,
	EMBEDDING_MODEL,
	OLLAMA_BASE_URL,
	OLLAMA_KEEP_ALIVE,
)

EMBEDDING_BATCH_SIZE = 32


def embed_texts(texts: list[str]) -> list[list[float]]:
	"""Return one Ollama embedding vector for each non-empty text."""
	if not texts or any(not text.strip() for text in texts):
		raise ValueError("Provide at least one non-empty text to embed.")

	all_embeddings: list[list[float]] = []
	for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
		batch = texts[start : start + EMBEDDING_BATCH_SIZE]
		body = json.dumps(
			{
				"model": EMBEDDING_MODEL,
				"input": batch,
				"keep_alive": OLLAMA_KEEP_ALIVE,
			}
		).encode("utf-8")
		request = Request(
			f"{OLLAMA_BASE_URL}/api/embed",
			data=body,
			headers={"Content-Type": "application/json"},
			method="POST",
		)
		with urlopen(request, timeout=120) as response:
			result = json.loads(response.read().decode("utf-8"))

		embeddings = result.get("embeddings")
		if not isinstance(embeddings, list) or len(embeddings) != len(batch):
			raise RuntimeError("Ollama returned an unexpected number of embeddings.")
		if any(len(vector) != EMBEDDING_DIMENSION for vector in embeddings):
			raise RuntimeError(
				f"Expected {EMBEDDING_DIMENSION}-dimensional embeddings from {EMBEDDING_MODEL}."
			)
		all_embeddings.extend(embeddings)
	return all_embeddings


def embed_text(text: str) -> list[float]:
	"""Embed one query or document chunk."""
	return embed_texts([text])[0]
