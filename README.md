# Dexian Medical Doctor

This is an early, local prototype that retrieves passages from an indexed
medical-reference collection and asks Ollama to draft an answer grounded in them.
It is not clinically validated and is not a substitute for a qualified clinician.

The local app supports separate chat threads with saved history and bounded context.
It does not yet have separate patient and doctor modes, doctor profiles, or a
clinician-reviewed safety policy. See [PRODUCT_REQUIREMENTS.md](./PRODUCT_REQUIREMENTS.md)
for the agreed product direction and boundaries.

## Setup and run (Windows PowerShell)

From the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

The project reads local settings from `.env` without requiring environment
activation. The checked-in `.env.example` shows the available options; `.env` is
ignored by Git and can hold machine-specific values.

Start Ollama separately. The configured embedding model must be `bge-m3` to match
the existing 1024-dimensional Qdrant vectors. The generation model defaults to
`qwen3:8b` unless overridden in `.env`. Start the API with the Python installation
that has the project dependencies:

```powershell
python -m uvicorn src.api.app:app --reload
```

Set `GENERATION_MODEL=qwen3:8b` in `.env` to use the downloaded model without
setting an environment variable every time. Restart the API after changing settings.
Ollama keeps the generation and embedding models loaded for up to 10 minutes after
their last request by default, reducing cold-start delays at the cost of using memory
while they remain loaded. Set `OLLAMA_KEEP_ALIVE` in `.env` to change this duration.

Keep that terminal open. In a browser, visit <http://127.0.0.1:8000/> to use the
chat app. Start a new chat, select an older chat to reopen it, or use × to delete a
chat. Select **Show sources for this answer** when you want citations. The Swagger
API explorer remains available at <http://127.0.0.1:8000/docs>.

Hover over a user message to retry its prompt, edit it inline, or copy it. Retrying
or saving an edit regenerates the reply and removes all later messages in that
conversation.

Chat threads and messages are saved locally in `data/chat_history.sqlite3`. The
complete thread is kept for reopening, while the model receives only recent turns
and, for longer chats, a compact summary of older turns from that same conversation.
Other chats are not included in the current chat's context. The summary is updated
when the thread grows beyond the recent-message window; this may add a model call.
The SQLite file is ignored by Git, but it is not encrypted. Use fictional or
non-identifying health details until privacy and security requirements have been
reviewed.

The chat API supports creating, listing, opening, and deleting conversations under
`/api/conversations`, and posting messages under
`/api/conversations/{conversation_id}/messages`. The original single-turn
`POST /api/ask` endpoint remains available.

Example request:

```json
{
  "question": "What do the medical references say about diabetes?",
  "limit": 5
}
```

## Guideline indexing

The local `qdrant_data` directory already contains an index. You do not need to
index the same material just to start the API. Index a document only when you
intend to add it to the searchable collection. Provide a real document path, not
the placeholder `path\to\guideline.pdf`.

Index one file:

```powershell
python scripts/run_ingestion.py "D:\path\to\guideline.pdf" --jurisdiction EG
```

Index supported files in a folder; `--limit` is optional:

```powershell
python scripts/index_supported_documents.py "D:\path\to\documents" --jurisdiction EG --limit 5
```

Supported formats are PDF, TXT, Markdown, NXML, XML, HTML, and HTM. The jurisdiction
must be `EG`, `EU`, or `US`. Indexing calls the configured Ollama embedding model
and writes vectors and passage metadata to local Qdrant.

Search without starting the API:

```powershell
python scripts/search_guidelines.py "diabetes" --limit 5
```

### Auditing the index and retrieval

To see how many chunks and source documents are indexed, their jurisdiction
distribution, and the sources contributing the most chunks, stop the API server
and run:

```powershell
python scripts/audit_guideline_index.py
```

The audit reads metadata only; it does not print stored medical passage text.
Use `--output evaluation/index-audit.md` to save a Markdown report. Metadata
extracted from NXML and PDF sources includes available titles, publisher, year,
DOI, and license details. The current StatPearls chapters are tagged
`jurisdiction=UNSPECIFIED`, `source_type=reference_chapter`, and
`guideline_status=not_verified`. A jurisdiction tag alone does not establish
that a source is an official guideline or is current.

To preview a metadata-only update for already indexed documents, stop the API
server and run:

```powershell
python scripts/backfill_document_metadata.py
```

If the preview is appropriate, apply it with:

```powershell
python scripts/backfill_document_metadata.py --apply
```

This updates Qdrant payload metadata without recomputing embeddings or changing
the indexed text. It also labels the existing StatPearls sources as jurisdiction
unspecified. Then rerun the audit to review metadata coverage.

Search now retrieves a wider candidate set and returns at most one passage per
source document, helping prevent several neighboring chunks from the same
document from crowding out other sources. It may return fewer passages than
requested when fewer distinct sources match.

## Guideline case evaluation

For a review-only run that creates fictional cases and model answers without
generating an answer key or calculating scores, use:

```powershell
python scripts/generate_case_report.py --count 10
```

The `--count` option accepts 1 to 1000 cases. It cycles through a broad list of
clinical specialties and subspecialties in order, so areas repeat only after the
full list has been covered. The script
retrieves medical-reference passages, creates each case, answers it using the
retrieved excerpts, and saves a Markdown report under `evaluation/reports/`.
The report contains each case, its question, model answer, and source references;
it has no retrieval or rubric scores. It appends each completed case to the
report, so completed cases remain available if a later request fails without
rewriting the entire report each time. Large runs may take a long time. Cases
and answers are unreviewed drafts for physician review. Use `--output` to choose
a report path, `--generation-limit` or `--answer-limit` to adjust passage counts,
and `--help` to see all options. The existing scored evaluator below is preserved
for future work.

Generate fictional cases from the local medical-reference index, evaluate the model's
diagnosis reasoning and treatment plan, and write a report in one command:

```powershell
python scripts/run_guideline_evaluation.py --count 10
```

The evaluation script retrieves from the indexed reference material without a
jurisdiction filter. Cases are
requested across cardiovascular, respiratory, infectious disease, endocrine,
gastrointestinal, neurology, renal/urinary, hematology, musculoskeletal, and
dermatology areas, so one run does not stay within a single condition. Cases are
generated one at a time using only passages from their own area to keep each
Ollama request within a manageable context. The script prints progress and updates
the report after each completed case, so completed results remain available if a
later request fails.

The Markdown report is written under `evaluation/reports/` and includes the full
case text, question, expected diagnosis and criteria, retrieved source/page/score
metadata, and model answer. The expected diagnosis is not sent to the answering
model. The report gives each case and the whole run a score out of 10: diagnosis
phrase match is worth 4 points, reasoning criteria 3 points, and treatment-plan
criteria 3 points. The overall score is the average across cases; source retrieval
is shown separately. These are case-insensitive phrase matches, not clinical
judgments. Cases and their generated answer keys are unreviewed drafts:
inspect each case, rubric, source, and answer manually before interpreting scores.
Use `--output` to choose a report path, and `--generation-limit` or
`--evaluation-limit` to change how many passages are retrieved at each stage. Run
`python scripts/run_guideline_evaluation.py --help` for all options.

## Project map

- `config/settings.py` — environment-based Ollama and Qdrant settings, embedding
  dimensions, and chunk sizes.
- `src/ingestion/parser.py` — extracts text and page/source metadata from supported
  document files.
- `src/ingestion/chunker.py` — splits extracted text into overlapping passages.
- `src/ingestion/embedder.py` — requests embeddings from Ollama.
- `src/vector_db/qdrant_client.py` — opens the local Qdrant database and ensures
  the collection exists.
- `src/vector_db/indexer.py` — `index_file(...)` stores document passages;
  `search_chunks(...)` retrieves matching passages.
- `src/rag/retriever.py` — validates retrieved passages and their citation metadata.
- `src/rag/generator.py` — sends the question and passages to Ollama for a grounded
  draft response and summarizes older turns when a thread's context window fills.
- `src/conversations/store.py` — persists chat threads, messages, and summary state
  in the local SQLite database.
- `src/conversations/context.py` — selects recent same-thread history and prepares
  older turns for summarization and contextual retrieval.
- `src/api/schemas.py`, `src/api/routes.py`, `src/api/app.py` — define request and
  response validation, chat and single-turn endpoints, and the FastAPI application.
- `src/api/static/index.html` — local browser interface for starting, reopening,
  and deleting chat threads.
- `scripts/run_ingestion.py` — command-line entry point for indexing one file.
- `scripts/index_supported_documents.py` — command-line entry point for indexing
  supported files under a folder.
- `scripts/search_guidelines.py` — command-line entry point for passage search.
- `scripts/run_guideline_evaluation.py` — generates cases, evaluates them, and
  writes a case-inclusive Markdown report in one run.
- `src/evaluation/benchmark.py` — benchmark validation and report generation.
- `tests/` — tests for parsing, retrieval, generation request construction, and API
  behavior.
- `requirements.txt` — runtime dependencies; `requirements-dev.txt` adds test tools.
- `PRODUCT_REQUIREMENTS.md` — agreed product scope, safety boundaries, and future
  requirements.
- `data/chat_history.sqlite3` — local, Git-ignored chat storage; do not add it to
  source control.

## Main function interfaces

- `extract_document_pages(file_path: str | Path) -> list[dict[str, str | int]]`
  — extract pages from one supported document.
- `chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]`
  — split text into passages; project defaults are in `config/settings.py`.
- `embed_texts(texts: list[str]) -> list[list[float]]` — embed one or more non-empty
  texts using Ollama. `embed_text(text: str)` is the single-text helper.
- `index_file(file_path: str, jurisdiction: str, client: QdrantClient | None = None) -> int`
  — extract, chunk, embed, and index a document; normal use is through the ingestion
  scripts.
- `search_chunks(query: str, limit: int = 5, jurisdiction: str | None = None, client: QdrantClient | None = None) -> list[dict[str, object]]`
  — search Qdrant; normal use is through the API or search script.
- `retrieve_guidelines(question: str, limit: int = 5, jurisdiction: str | None = None) -> list[GuidelinePassage]`
  — retrieve validated, citation-ready passages for application use.
- `generate_grounded_answer(question: str, passages: list[GuidelinePassage]) -> str`
  — generate from non-empty retrieved passages; normal use is through the API.

Run tests with:

```powershell
python -m pytest
```

Local guideline documents, the Qdrant database, virtual environment, and environment
files are excluded from Git. Do not commit private or licensed source material.
