"""
Shared application state.
This module provides the in-memory NOTEBOOKS dictionary shared across all endpoints.
"""
from typing import Dict
from app.models import Notebook

# In-memory notebook storage
# Key: notebook_id, Value: Notebook instance
NOTEBOOKS: Dict[str, Notebook] = {}

__all__ = ["NOTEBOOKS"]

