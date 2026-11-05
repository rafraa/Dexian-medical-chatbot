from qdrant_client import QdrantClient
from qdrant_client.http import models
from config.settings import EMBEDDING_DIMENSION, QDRANT_COLLECTION, QDRANT_PATH


def get_qdrant_client() -> QdrantClient:
	"""Open Qdrant's local on-disk database."""
	return QdrantClient(path=str(QDRANT_PATH))


def ensure_collection(client: QdrantClient) -> None:
	"""Create the DMD collection if it does not exist."""
	if not client.collection_exists(QDRANT_COLLECTION):
		client.create_collection(
			collection_name=QDRANT_COLLECTION,
			vectors_config=models.VectorParams(
				size=EMBEDDING_DIMENSION,
				distance=models.Distance.COSINE,
			),
		)
