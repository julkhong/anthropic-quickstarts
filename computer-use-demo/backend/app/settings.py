from __future__ import annotations

import os


def get_database_url() -> str:
    # Example: postgresql+psycopg://cu:cu@db:5432/cu
    url = os.getenv("DATABASE_URL")
    if not url:
        # Fallback to local sqlite if not provided (useful for dev without Docker DB)
        return "sqlite+aiosqlite:///./dev.db"
    return url


