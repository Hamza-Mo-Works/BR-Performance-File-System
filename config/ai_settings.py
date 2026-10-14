"""Defaults for a small RAG demonstration. Credentials are supplied separately."""
CHAT_MODEL = "gpt-4.1-mini"
EMBEDDING_MODEL = "text-embedding-3-small"
RETRIEVAL_TOP_K = 5
# Demo heuristic, not a calibrated measure of answer correctness.
MIN_SIMILARITY = 0.25
MAX_QUESTION_CHARS = 2000
API_TIMEOUT_SECONDS = 45
CHAT_MAX_TOKENS = 2400
