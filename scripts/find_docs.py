import os
import json
from identify import identify

INCLUDE_TAGS = {"markdown", "rst", "adoc"}
INCLUDE_EXTS = {".md", ".markdown", ".rst", ".txt", ".adoc", ".ipynb"}


def is_likely_doc_file(filepath):
    try:
        tags = identify.tags_from_path(filepath)
        if INCLUDE_TAGS.intersection(tags):
            return True
    except Exception:
        pass

    ext = os.path.splitext(filepath)[1].lower()
    return ext in INCLUDE_EXTS


def find_likely_doc_files(root_dir):
    doc_files = []

    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if is_likely_doc_file(filepath):
                rel_path = os.path.relpath(filepath, start=root_dir)
                doc_files.append(rel_path)

    return doc_files


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python find_docs.py /path/to/repo")
        sys.exit(1)

    root = sys.argv[1]
    docs = find_likely_doc_files(root)
    print(json.dumps(docs, indent=2))
