import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.is_file():
	for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
		line = line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", maxsplit=1)
		key = key.strip()
		value = value.strip()
		if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
			value = value[1:-1]
		if key:
			os.environ.setdefault(key, value)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "qwen3:8b")
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")
EMBEDDING_DIMENSION = 1024
QDRANT_PATH = Path(os.getenv("QDRANT_PATH", "qdrant_data"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "dmd_medical_guidelines")
CHAT_DB_PATH = Path(os.getenv("CHAT_DB_PATH", "data/chat_history.sqlite3"))
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
