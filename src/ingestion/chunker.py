def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
	"""Split text into overlapping character windows, preferring word boundaries."""
	if chunk_size <= 0:
		raise ValueError("chunk_size must be positive.")
	if overlap < 0 or overlap >= chunk_size:
		raise ValueError("overlap must be non-negative and smaller than chunk_size.")

	text = " ".join(text.split())
	chunks: list[str] = []
	start = 0

	while start < len(text):
		end = min(start + chunk_size, len(text))
		if end < len(text):
			boundary = text.rfind(" ", start + chunk_size // 2, end)
			if boundary > start:
				end = boundary
		chunk = text[start:end].strip()
		if chunk:
			chunks.append(chunk)
		if end == len(text):
			break
		start = max(end - overlap, start + 1)

	return chunks
