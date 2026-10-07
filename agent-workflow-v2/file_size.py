"""Measure source-file token size independently of lines, bytes or model inference."""
from functools import lru_cache

SOURCE_TOKEN_LIMIT=8192
SOURCE_TOKEN_TARGET=4096


@lru_cache(maxsize=32)
def source_tokens(text):
    """Use the local executor tokenizer; bounded caching avoids repeated tokenization."""
    from shadow_navigation import count
    return count(text)
