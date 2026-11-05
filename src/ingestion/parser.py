from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from pypdf import PdfReader


def _clean_text(text: str) -> str:
	"""Normalize repeated whitespace in extracted document content."""
	return " ".join(text.replace("\xa0", " ").replace("\u200b", " ").split())


def _extract_nxml_text(path: Path) -> str:
	"""Extract readable text from an NXML document."""
	try:
		root = ET.parse(str(path)).getroot()
	except ET.ParseError:
		return ""

	parts: list[str] = []
	for node in root.iter():
		text = node.text or ""
		if text and text.strip():
			parts.append(_clean_text(text))
	for node in root.iter():
		if node.tail and node.tail.strip():
			parts.append(_clean_text(node.tail))
	return "\n\n".join(parts).strip()


def _xml_local_name(tag: str) -> str:
	return tag.rsplit("}", maxsplit=1)[-1]


def _element_text(element: ET.Element) -> str:
	return _clean_text(" ".join(element.itertext()))


def _first_element_text(
	root: ET.Element,
	*names: str,
	parent_name: str | None = None,
) -> str:
	for parent in root.iter():
		if parent_name is not None and _xml_local_name(parent.tag) != parent_name:
			continue
		for node in parent.iter():
			if _xml_local_name(node.tag) in names:
				text = _element_text(node)
				if text:
					return text
	return ""


def extract_document_metadata(file_path: str | Path) -> dict[str, str]:
	"""Extract identifiers and descriptive metadata available in the source file."""
	path = Path(file_path)
	suffix = path.suffix.lower()
	if suffix in {".nxml", ".xml"}:
		return _nxml_metadata(path)
	metadata = {
		"title": path.stem,
		"document_type": suffix.lstrip(".").upper() or "document",
	}
	if suffix == ".pdf":
		pdf_metadata = PdfReader(str(path)).metadata
		if pdf_metadata and pdf_metadata.title:
			metadata["title"] = _clean_text(pdf_metadata.title)
		if pdf_metadata and pdf_metadata.author:
			metadata["author"] = _clean_text(pdf_metadata.author)
		metadata["source_type"] = "document"
		metadata["guideline_status"] = "not_verified"
	return metadata


def _nxml_metadata(path: Path) -> dict[str, str]:
	try:
		root = ET.parse(str(path)).getroot()
	except ET.ParseError:
		return {"title": path.stem, "document_type": path.suffix.lstrip(".").upper()}

	root_name = _xml_local_name(root.tag)
	if root_name == "book-part-wrapper":
		title = _first_element_text(root, "title", parent_name="book-part-meta")
		document_type = "book chapter"
		book_title = _first_element_text(root, "book-title", parent_name="book-meta")
	else:
		title = _first_element_text(root, "article-title", parent_name="article-meta")
		document_type = "journal article" if root_name == "article" else "XML document"

	metadata: dict[str, str] = {
		"title": title or path.stem,
		"document_type": document_type,
		"source_type": (
			"reference_chapter"
			if document_type == "book chapter"
			else "research_article"
			if document_type == "journal article"
			else "unknown"
		),
		"guideline_status": "not_verified",
	}
	publisher = _first_element_text(root, "publisher-name")
	if publisher:
		metadata["publisher"] = publisher
		if publisher.casefold() == "statpearls publishing":
			metadata["jurisdiction"] = "UNSPECIFIED"

	if root_name == "article":
		journal = _first_element_text(root, "journal-title", parent_name="journal-meta")
		if journal:
			metadata["journal"] = journal
		article_type = root.attrib.get("article-type", "").strip()
		if article_type:
			metadata["article_type"] = article_type
	elif root_name == "book-part-wrapper" and book_title:
		metadata["book_title"] = book_title

	publication_year = _first_element_text(root, "year", parent_name="pub-date")
	if publication_year:
		metadata["publication_year"] = publication_year

	for node in root.iter():
		node_name = _xml_local_name(node.tag)
		if node_name in {"pub-id", "article-id", "book-id"}:
			id_type_key = (
				"book-id-type" if node_name == "book-id" else "pub-id-type"
			)
			if node.attrib.get(id_type_key, "").casefold() == "doi":
				doi = _element_text(node)
				if doi:
					metadata["doi"] = doi
					break

	for node in root.iter():
		if _xml_local_name(node.tag) != "license":
			continue
		license_type = next(
			(value for key, value in node.attrib.items() if _xml_local_name(key) == "license-type"),
			"",
		)
		license_url = next(
			(value for key, value in node.attrib.items() if _xml_local_name(key) == "href"),
			"",
		)
		license_description = _first_element_text(node, "license-p")
		license_value = license_type or license_description
		if license_value:
			metadata["license"] = license_value
		if license_url:
			metadata["license_url"] = license_url
		break

	return metadata


def _extract_html_text(path: Path) -> str:
	"""Strip most HTML tags while preserving readable text."""
	text = path.read_text(encoding="utf-8", errors="ignore")
	text = re.sub(r"<script.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
	text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
	text = re.sub(r"<[^>]+>", " ", text)
	return _clean_text(text)


def extract_pdf_pages(pdf_path: str | Path) -> list[dict[str, str | int]]:
	"""Extract selectable text from a PDF, preserving its one-based page number."""
	path = Path(pdf_path)
	reader = PdfReader(str(path))
	pages: list[dict[str, str | int]] = []
	for page_number, page in enumerate(reader.pages, start=1):
		text = (page.extract_text() or "").strip()
		if text:
			pages.append({"text": text, "page": page_number, "source": str(path)})
	return pages


def extract_document_pages(file_path: str | Path) -> list[dict[str, str | int]]:
	"""Extract text from PDF, plain text, or XML-like scientific source documents."""
	path = Path(file_path)
	suffix = path.suffix.lower()

	if suffix == ".pdf":
		metadata = extract_document_metadata(path)
		return [
			{**page, **metadata}
			for page in extract_pdf_pages(path)
		]

	if suffix in {".txt", ".md"}:
		text = path.read_text(encoding="utf-8", errors="ignore").strip()
		if not text:
			return []
		return [
			{
				"text": _clean_text(text),
				"page": 1,
				"source": str(path),
				**extract_document_metadata(path),
			}
		]

	if suffix in {".nxml", ".xml"}:
		text = _extract_nxml_text(path)
		if not text:
			return []
		return [
			{
				"text": text,
				"page": 1,
				"source": str(path),
				**extract_document_metadata(path),
			}
		]

	if suffix in {".html", ".htm"}:
		text = _extract_html_text(path)
		if not text:
			return []
		return [
			{
				"text": text,
				"page": 1,
				"source": str(path),
				**extract_document_metadata(path),
			}
		]

	raise ValueError(f"Unsupported input type: {path.suffix or 'unknown'}")
