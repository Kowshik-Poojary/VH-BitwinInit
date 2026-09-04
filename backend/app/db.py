"""MongoDB connection for the LeakGuard backend."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

_client: MongoClient | None = None


def get_db() -> Database:
    global _client
    if _client is None:
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI environment variable is not set")
        _client = MongoClient(uri)
    return _client["leakguard"]
