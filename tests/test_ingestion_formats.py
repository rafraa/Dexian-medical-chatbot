from pathlib import Path

from src.ingestion.parser import extract_document_metadata, extract_document_pages


def test_extract_document_pages_handles_txt(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("Alpha beta\nGamma delta\n", encoding="utf-8")

    pages = extract_document_pages(file_path)

    assert len(pages) == 1
    assert pages[0]["page"] == 1
    assert "Alpha beta" in pages[0]["text"]
    assert "Gamma delta" in pages[0]["text"]


def test_extract_document_pages_handles_nxml(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.nxml"
    file_path.write_text(
        """
        <book-part-wrapper xmlns:xlink="http://www.w3.org/1999/xlink">
          <body>
            <sec>
              <title>Title</title>
              <p>Alpha beta</p>
            </sec>
          </body>
        </book-part-wrapper>
        """,
        encoding="utf-8",
    )

    pages = extract_document_pages(file_path)

    assert len(pages) == 1
    assert pages[0]["page"] == 1
    assert "Alpha beta" in pages[0]["text"]


def test_extract_nxml_metadata_for_book_chapter(tmp_path: Path) -> None:
    file_path = tmp_path / "chapter.nxml"
    file_path.write_text(
        """
        <book-part-wrapper xmlns:xlink="http://www.w3.org/1999/xlink">
          <book-meta>
            <book-title>Clinical Reference</book-title>
            <publisher><publisher-name>Example Publisher</publisher-name></publisher>
            <pub-date><year>2024</year></pub-date>
            <permissions>
              <license license-type="open-access" xlink:href="https://example.test/license">
                <license-p>Example license</license-p>
              </license>
            </permissions>
          </book-meta>
          <book-part-meta>
            <title-group><title>Specific Chapter</title></title-group>
            <book-id book-id-type="doi">10.1234/example.chapter</book-id>
          </book-part-meta>
          <body><p>Chapter content.</p></body>
        </book-part-wrapper>
        """,
        encoding="utf-8",
    )

    metadata = extract_document_metadata(file_path)
    pages = extract_document_pages(file_path)

    assert metadata == {
        "title": "Specific Chapter",
        "document_type": "book chapter",
        "source_type": "reference_chapter",
        "guideline_status": "not_verified",
        "book_title": "Clinical Reference",
        "publisher": "Example Publisher",
        "publication_year": "2024",
        "doi": "10.1234/example.chapter",
        "license": "open-access",
        "license_url": "https://example.test/license",
    }
    assert pages[0]["title"] == "Specific Chapter"
    assert pages[0]["publisher"] == "Example Publisher"


def test_extract_nxml_metadata_for_article(tmp_path: Path) -> None:
    file_path = tmp_path / "article.nxml"
    file_path.write_text(
        """
        <article article-type="research-article">
          <front>
            <journal-meta>
              <journal-title>Example Journal</journal-title>
              <publisher><publisher-name>Example Publisher</publisher-name></publisher>
            </journal-meta>
            <article-meta>
              <title-group><article-title>Article Title</article-title></title-group>
              <pub-date><year>2025</year></pub-date>
              <article-id pub-id-type="doi">10.5678/example.article</article-id>
            </article-meta>
          </front>
          <body><p>Article content.</p></body>
        </article>
        """,
        encoding="utf-8",
    )

    metadata = extract_document_metadata(file_path)

    assert metadata["title"] == "Article Title"
    assert metadata["document_type"] == "journal article"
    assert metadata["article_type"] == "research-article"
    assert metadata["journal"] == "Example Journal"
    assert metadata["publisher"] == "Example Publisher"
    assert metadata["publication_year"] == "2025"
    assert metadata["doi"] == "10.5678/example.article"
