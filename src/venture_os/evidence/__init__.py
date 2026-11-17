"""Evidence pipeline: store fetched pages (documents + chunks), extract quoted claims, check them by rules."""

# Evidence items: the format Phases 1-2 write and Phase 3 (Build) reads (see items.py).
from venture_os.evidence.items import LABEL_TEXT, Item, add, load, runs_dir

__all__ = ["LABEL_TEXT", "Item", "add", "load", "runs_dir"]
