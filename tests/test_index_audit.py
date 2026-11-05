import pytest

import scripts.audit_guideline_index as audit_script


class FakeRecord:
	def __init__(self, payload):
		self.payload = payload


class FakeClient:
	def __init__(self):
		self.calls = 0
		self.closed = False

	def collection_exists(self, _collection_name):
		return True

	def scroll(self, **kwargs):
		self.calls += 1
		assert kwargs["with_vectors"] is False
		if self.calls == 1:
			return (
				[
					FakeRecord(
						{
							"source": "guide.pdf",
							"page": 1,
							"jurisdiction": "US",
							"source_type": "reference_chapter",
							"guideline_status": "not_verified",
							"title": "Example guideline",
							"publisher": "Example publisher",
							"publication_year": "2025",
							"doi": "10.1234/guideline",
							"license": "open-access",
							"license_url": "https://example.test/license",
							"document_type": "journal article",
						}
					),
					FakeRecord(
						{
							"source": "guide.pdf",
							"page": 2,
							"jurisdiction": "US",
						}
					),
				],
				"next-page",
			)
		return (
			[
				FakeRecord({"source": "another.pdf", "page": 1, "jurisdiction": "EU"}),
				FakeRecord({"text": "missing metadata"}),
			],
			None,
		)


def test_audit_index_counts_sources_jurisdictions_and_missing_metadata() -> None:
	client = FakeClient()

	audit = audit_script.audit_index(client)

	assert audit["total_chunks"] == 4
	assert audit["unique_sources"] == 2
	assert audit["jurisdiction_chunks"] == {"EU": 1, "US": 2}
	assert audit["missing_source_chunks"] == 1
	assert audit["missing_jurisdiction_chunks"] == 1
	assert audit["sources"][0] == {
		"source": "guide.pdf",
		"chunks": 2,
		"pages": 2,
		"jurisdictions": ["US"],
		"source_type": "reference_chapter",
		"guideline_status": "not_verified",
		"title": "Example guideline",
		"publisher": "Example publisher",
		"publication_year": "2025",
		"doi": "10.1234/guideline",
		"license": "open-access",
		"license_url": "https://example.test/license",
		"document_type": "journal article",
	}
	assert audit["metadata_source_counts"]["title"] == 1


def test_audit_index_requires_existing_collection(monkeypatch) -> None:
	class MissingCollectionClient:
		def collection_exists(self, _collection_name):
			return False

		def close(self):
			pass

	monkeypatch.setattr(audit_script, "get_qdrant_client", MissingCollectionClient)

	with pytest.raises(RuntimeError, match="does not exist"):
		audit_script.audit_index()


def test_format_report_explains_metadata_gaps() -> None:
	report = audit_script.format_report(
		{
			"collection": "guidelines",
			"total_chunks": 4,
			"unique_sources": 2,
			"missing_source_chunks": 0,
			"missing_jurisdiction_chunks": 0,
			"jurisdiction_chunks": {"US": 4},
			"metadata_source_counts": {"title": 1, "doi": 1},
			"sources": [
				{
					"source": "guide.nxml",
					"title": "Example Guideline",
					"chunks": 4,
					"pages": 1,
					"jurisdictions": ["US"],
					"source_type": "reference_chapter",
					"guideline_status": "not_verified",
					"publisher": "Example Publisher",
					"publication_year": "2024",
					"doi": "10.1234/example",
					"license": "open-access",
				}
			],
		},
		top_sources=10,
	)

	assert "Source type and guideline status" in report
	assert "Example Guideline" in report
	assert "source type: reference_chapter" in report
	assert "guideline status: not_verified" in report
	assert "publisher: Example Publisher" in report
	assert "journal: " not in report
