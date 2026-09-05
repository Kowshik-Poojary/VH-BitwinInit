"""Resilient Database layer for the LeakGuard backend.

Connects to MongoDB if MONGODB_URI is provided and reachable.
Otherwise, transparently falls back to an embedded JSON-backed document store
at backend/data/leakguard_store.json, guaranteeing 100% zero-configuration startup.
"""

from __future__ import annotations

import copy
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STORE_FILE = DATA_DIR / "leakguard_store.json"


class InsertResult:
    def __init__(self, inserted_id: Any):
        self.inserted_id = inserted_id


class LocalCursor:
    def __init__(self, docs: list[dict]):
        self._docs = docs

    def sort(self, key_or_list: Any, direction: int = 1) -> LocalCursor:
        if isinstance(key_or_list, list):
            for k, d in reversed(key_or_list):
                self._docs.sort(key=lambda x: str(x.get(k, "")), reverse=(d == -1))
        else:
            self._docs.sort(key=lambda x: str(x.get(key_or_list, "")), reverse=(direction == -1))
        return self

    def limit(self, count: int) -> list[dict]:
        return [copy.deepcopy(d) for d in self._docs[:count]]

    def __iter__(self):
        return iter([copy.deepcopy(d) for d in self._docs])

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [copy.deepcopy(d) for d in self._docs[index]]
        return copy.deepcopy(self._docs[index])

    def __len__(self):
        return len(self._docs)


class LocalCollection:
    def __init__(self, name: str, db: LocalDatabase):
        self.name = name
        self.db = db

    def _matches(self, doc: dict, query: dict) -> bool:
        for k, v in query.items():
            if isinstance(v, dict):
                if "$ne" in v:
                    if doc.get(k) == v["$ne"]:
                        return False
                if "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        return False
            else:
                if doc.get(k) != v:
                    return False
        return True

    def find(self, query: dict | None = None) -> LocalCursor:
        query = query or {}
        items = [d for d in self.db._get_data(self.name) if self._matches(d, query)]
        return LocalCursor(items)

    def find_one(self, query: dict | None = None, sort: list | None = None) -> dict | None:
        query = query or {}
        cursor = self.find(query)
        if sort:
            cursor.sort(sort)
        docs = list(cursor)
        return copy.deepcopy(docs[0]) if docs else None

    def insert_one(self, doc: dict) -> InsertResult:
        doc_copy = copy.deepcopy(doc)
        if "_id" not in doc_copy:
            doc_copy["_id"] = str(uuid.uuid4())
        self.db._insert(self.name, doc_copy)
        return InsertResult(doc_copy["_id"])

    def update_one(self, query: dict, update: dict, upsert: bool = False) -> None:
        items = self.db._get_data(self.name)
        matched_idx = None
        for idx, d in enumerate(items):
            if self._matches(d, query):
                matched_idx = idx
                break

        if matched_idx is not None:
            doc = items[matched_idx]
            if "$set" in update:
                doc.update(copy.deepcopy(update["$set"]))
            self.db._save()
        elif upsert:
            new_doc = copy.deepcopy(query)
            if "$set" in update:
                new_doc.update(copy.deepcopy(update["$set"]))
            if "$setOnInsert" in update:
                new_doc.update(copy.deepcopy(update["$setOnInsert"]))
            if "_id" not in new_doc:
                new_doc["_id"] = str(uuid.uuid4())
            self.db._insert(self.name, new_doc)

    def count_documents(self, query: dict | None = None) -> int:
        query = query or {}
        return sum(1 for d in self.db._get_data(self.name) if self._matches(d, query))

    def distinct(self, key: str) -> list[Any]:
        seen = set()
        res = []
        for d in self.db._get_data(self.name):
            val = d.get(key)
            if val is not None and val not in seen:
                seen.add(val)
                res.append(val)
        return res

    def aggregate(self, pipeline: list[dict]) -> list[dict]:
        docs = [copy.deepcopy(d) for d in self.db._get_data(self.name)]
        for stage in pipeline:
            if "$match" in stage:
                docs = [d for d in docs if self._matches(d, stage["$match"])]
            elif "$sort" in stage:
                sort_spec = stage["$sort"]
                for k, d in reversed(list(sort_spec.items())):
                    docs.sort(key=lambda x: str(x.get(k, "")), reverse=(d == -1))
            elif "$group" in stage:
                group_spec = stage["$group"]
                id_expr = group_spec.get("_id")
                groups: dict[Any, list[dict]] = {}
                for d in docs:
                    if isinstance(id_expr, str) and id_expr.startswith("$"):
                        val = d.get(id_expr[1:])
                    else:
                        val = id_expr
                    groups.setdefault(val, []).append(d)

                result = []
                for gid, group_docs in groups.items():
                    row = {"_id": gid}
                    for field, agg in group_spec.items():
                        if field == "_id":
                            continue
                        if "$sum" in agg:
                            sum_expr = agg["$sum"]
                            if sum_expr == 1:
                                row[field] = len(group_docs)
                            elif isinstance(sum_expr, str) and sum_expr.startswith("$"):
                                key_path = sum_expr[1:].split(".")
                                total = 0
                                for gd in group_docs:
                                    cur = gd
                                    for kp in key_path:
                                        if isinstance(cur, dict):
                                            cur = cur.get(kp, 0)
                                        else:
                                            cur = 0
                                    total += (cur or 0)
                                row[field] = total
                        elif "$first" in agg:
                            first_expr = agg["$first"]
                            if isinstance(first_expr, str) and first_expr.startswith("$"):
                                key = first_expr[1:]
                                row[field] = group_docs[0].get(key) if group_docs else None
                        elif "$addToSet" in agg:
                            add_expr = agg["$addToSet"]
                            if isinstance(add_expr, str) and add_expr.startswith("$"):
                                key = add_expr[1:]
                                row[field] = list({gd.get(key) for gd in group_docs})
                    result.append(row)
                docs = result
        return docs


class LocalDatabase:
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self._data: dict[str, list[dict]] = {}
        self._load()

    def _default_serializer(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)

    def _load(self) -> None:
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, default=self._default_serializer)
        except Exception:
            pass

    def _get_data(self, col: str) -> list[dict]:
        return self._data.setdefault(col, [])

    def _insert(self, col: str, doc: dict) -> None:
        self._get_data(col).append(doc)
        self._save()

    def __getitem__(self, name: str) -> LocalCollection:
        return LocalCollection(name, self)


_client = None
_local_db: LocalDatabase | None = None


def get_db() -> Any:
    global _client, _local_db
    uri = os.environ.get("MONGODB_URI")
    if uri:
        try:
            from pymongo import MongoClient
            if _client is None:
                _client = MongoClient(uri, serverSelectionTimeoutMS=2000)
                # quick probe
                _client.admin.command("ping")
            return _client["leakguard"]
        except Exception:
            pass

    if _local_db is None:
        _local_db = LocalDatabase(STORE_FILE)
    return _local_db
