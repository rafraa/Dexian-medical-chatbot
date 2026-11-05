from pathlib import Path
from types import SimpleNamespace

import scripts.backfill_document_metadata as backfill


class FakeClient:
	def __init__(self, source: str):
		self.source = source
		self.scroll_calls = 0
		self.updated = []
		self.closed = False

	def collection_exists(self, _collection_name):
		return True

	def scroll(self, **_kwargs):
		self.scroll_calls += 1
		if self.scroll_calls == 1:
			return (
				[
					SimpleNamespace(payload={"source": self.source}),
					SimpleNamespace(payload={"source": self.source}),
				],
				None,
			)
		raise AssertionError("Unexpected additional scroll.")

	def set_payload(self, **kwargs):
		self.updated.append(kwargs)

	def close(self):
		self.closed = True


def test_backfill_updates_unique_sources_without_touching_vectors(
	monkeypatch,
	tmp_path: Path,
) -> None:
	source_file = tmp_path / "source.nxml"
	source_file.write_text("<article/>", encoding="utf-8")
	client = FakeClient(str(source_file))
	monkeypatch.setattr(
		backfill,
		"extract_document_metadata",
		lambda _path: {"title": "Example", "document_type": "journal article"},
	)

	result = backfill.backfill_metadata(apply_changes=True, client=client)

	assert result == {
		"sources_found": 1,
		"sources_updated": 1,
		"missing_source_files": 0,
	}
	assert len(client.updated) == 1
	assert client.updated[0]["payload"]["title"] == "Example"
	assert client.updated[0]["wait"] is True
	assert not client.closed


def test_backfill_dry_run_does_not_update_index(
	monkeypatch,
	tmp_path: Path,
) -> None:
	source_file = tmp_path / "source.nxml"
	source_file.write_text("<article/>", encoding="utf-8")
	client = FakeClient(str(source_file))
	monkeypatch.setattr(
		backfill,
		"extract_document_metadata",
		lambda _path: {"title": "Example"},
	)

	result = backfill.backfill_metadata(client=client)

	assert result["sources_ready"] == 1
	assert client.updated == []
