from typing import Optional
from .base import StorageBackend
from .file_storage import FileStorage
from .dynamodb_storage import DynamoDBStorage
from app.core import settings


_storage_backend: Optional[StorageBackend] = None


def get_storage() -> StorageBackend:
    """Get the configured storage backend (singleton)"""
    global _storage_backend
    
    if _storage_backend is None:
        if settings.DYNAMODB_ENABLED and settings.DYNAMODB_TABLE_NAME:
            _storage_backend = DynamoDBStorage()
        else:
            _storage_backend = FileStorage()
    
    return _storage_backend


# Convenience functions for backward compatibility
async def save_notebook(notebook, subdirectory=None):
    storage = get_storage()
    if hasattr(storage, 'save_notebook'):
        if isinstance(storage, FileStorage) and subdirectory:
            return await storage.save_notebook(notebook, subdirectory)
        return await storage.save_notebook(notebook)


async def load_notebook(notebook_id, user_id=None, subdirectory=None):
    storage = get_storage()
    if isinstance(storage, FileStorage) and subdirectory:
        return await storage.load_notebook(user_id or "", notebook_id, subdirectory)
    elif isinstance(storage, DynamoDBStorage):
        if user_id:
            return await storage.load_notebook(user_id, notebook_id)
        else:
            return await storage.load_notebook_by_id(notebook_id)
    else:
        return await storage.load_notebook(user_id or "", notebook_id)


async def list_notebooks(user_id=None):
    return await get_storage().list_notebooks(user_id)


async def delete_notebook(notebook_id, user_id):
    return await get_storage().delete_notebook(notebook_id, user_id)


# For backwards compatibility
DYNAMODB_ENABLED = settings.DYNAMODB_ENABLED


__all__ = [
    "StorageBackend", "FileStorage", "DynamoDBStorage",
    "get_storage", "save_notebook", "load_notebook",
    "list_notebooks", "delete_notebook", "DYNAMODB_ENABLED"
]

