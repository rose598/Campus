from pathlib import Path

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

with open(_SCHEMA_PATH, "r", encoding="utf-8") as _f:
    SCHEMA_SQL = _f.read()
