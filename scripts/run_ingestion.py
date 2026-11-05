import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from src.vector_db.indexer import index_file


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Index a medical guideline file (PDF, TXT, NXML, HTML) in local Qdrant."
	)
	parser.add_argument("input_file", help="Path to the document or guideline file to index")
	parser.add_argument("--jurisdiction", required=True, choices=["EG", "EU", "US"])
	args = parser.parse_args()

	count = index_file(args.input_file, args.jurisdiction)
	print(f"Indexed {count} chunks from {args.input_file}.")


if __name__ == "__main__":
	main()
