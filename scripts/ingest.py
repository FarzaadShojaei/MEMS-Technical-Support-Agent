"""Ingest the corpus in data/raw/ into the vector index.

Handles:
  - .pdf  (datasheets, app notes)   -> per-page text extraction via PyMuPDF
  - .md / .txt / .c / .h            -> read as plain text (driver README, examples)

Usage:
    python scripts/ingest.py            # ingest everything in data/raw/
    python scripts/ingest.py --reset    # wipe the index first
"""

import argparse
import shutil
import sys
from pathlib import Path

import fitz  # PyMuPDF

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.rag import store  # noqa: E402
from app.rag.chunking import Chunk, chunk_text  # noqa: E402

TEXT_SUFFIXES = {".md", ".txt", ".c", ".h"}


def ingest_pdf(path: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    with fitz.open(path) as doc:
        for page_no, page in enumerate(doc, start=1):
            text = page.get_text("text")
            chunks.extend(
                chunk_text(text, source=path.name, page=page_no,
                           chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)
            )
    return chunks


def ingest_textfile(path: Path) -> list[Chunk]:
    text = path.read_text(errors="ignore")
    return chunk_text(text, source=path.name, page=1,
                      chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="wipe the index before ingesting")
    args = parser.parse_args()

    if args.reset:
        shutil.rmtree(settings.index_dir, ignore_errors=True)
        print(f"Reset index at {settings.index_dir}")

    raw = Path(settings.raw_data_dir)
    files = [p for p in sorted(raw.glob("*")) if p.suffix.lower() == ".pdf" or p.suffix.lower() in TEXT_SUFFIXES]
    if not files:
        print(f"No ingestable files found in {raw}/ — put the datasheet PDF there first.")
        sys.exit(1)

    total = 0
    for path in files:
        chunks = ingest_pdf(path) if path.suffix.lower() == ".pdf" else ingest_textfile(path)
        n = store.add_chunks(chunks)
        total += n
        print(f"  {path.name}: {n} chunks")

    print(f"Done. {total} chunks indexed ({store.count()} total in collection '{settings.collection_name}').")


if __name__ == "__main__":
    main()
