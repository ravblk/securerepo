"""Stable Qdrant ids for ingested policy chunks.

Page id and chunk index are packed into one integer. String concatenation
(`f"{page_id}{chunk:02d}"`) aliases distinct pairs, for example
`(1, 234)` and `(12, 34)` both become `1234` and overwrite each other.
"""

CHUNK_SPACE = 1_000_000


def policy_point_id(page_id, chunk_idx: int) -> int:
    """Return a positive integer id unique for `(page_id, chunk_idx)`."""
    page = int(page_id)
    chunk = int(chunk_idx)
    if page < 0 or chunk < 0:
        raise ValueError("page_id and chunk_idx must be non-negative")
    if chunk >= CHUNK_SPACE:
        raise ValueError(f"chunk_idx must be < {CHUNK_SPACE}")
    return page * CHUNK_SPACE + chunk
