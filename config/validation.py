"""Limits for the synthetic upload workflow. No provider or API-key settings."""
MAX_UPLOAD_BYTES = 1024 * 1024
MAX_HEADER_BYTES = 16 * 1024
MAX_NOTE_CHARS = 4000
MAX_METADATA_CHARS = 200
SUPPORTED_TUNES = ("Stage 1",)

REQUIRED_METADATA = (
    "make", "model", "engine", "ecu_family", "hardware_id", "software_id",
    "read_method", "transmission", "fuel_spec", "hardware_configuration",
)
