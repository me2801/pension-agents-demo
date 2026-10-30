"""Write the OpenAPI spec to a file; the frontend generates its TypeScript types from it.

Usage:  uv run python -m scripts.export_openapi openapi.json
"""

import json
import sys
from pathlib import Path

from pydantic import SecretStr

from app.config import Settings
from app.main import create_app


def main(path: str) -> None:
    """Build the app without starting it (no database needed) and dump its spec."""
    settings = Settings(database_url="postgresql+psycopg://unused", jwt_secret=SecretStr("x" * 32))
    spec = create_app(settings).openapi()
    Path(path).write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
