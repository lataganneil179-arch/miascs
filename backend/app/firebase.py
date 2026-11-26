"""Firebase Admin initialisation and Firestore client."""

import json
from threading import Lock
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from .config import get_settings

_app: firebase_admin.App | None = None
_db: Any = None
_lock = Lock()


def init_firebase() -> firebase_admin.App:
    """Initialise the Admin SDK from an inline JSON blob, a file, or ADC."""
    global _app
    with _lock:
        if _app is not None:
            return _app

        settings = get_settings()
        if settings.service_account_json:
            cred = credentials.Certificate(json.loads(settings.service_account_json))
        elif settings.service_account_file:
            cred = credentials.Certificate(settings.service_account_file)
        else:
            cred = credentials.ApplicationDefault()

        options = {"projectId": settings.project_id} if settings.project_id else None
        _app = firebase_admin.initialize_app(cred, options)
        return _app


def db() -> Any:
    """Return a cached Firestore client."""
    global _db
    if _db is None:
        init_firebase()
        with _lock:
            if _db is None:
                _db = firestore.client()
    return _db


def query_equals(collection: str, **filters: Any) -> Any:
    """Build a query of equality filters (no composite index required)."""
    query = db().collection(collection)
    for field, value in filters.items():
        query = query.where(filter=FieldFilter(field, "==", value))
    return query
