from abc import ABC, abstractmethod
from typing import List, Optional
from app.models import Notebook


class StorageBackend(ABC):
    """Abstract base class for notebook storage backends"""
    
    @abstractmethod
    async def save_notebook(self, notebook: Notebook) -> None:
        """Save a notebook to storage"""
        pass
    
    @abstractmethod
    async def load_notebook(self, user_id: str, notebook_id: str) -> Optional[Notebook]:
        """Load a notebook from storage"""
        pass
    
    @abstractmethod
    async def list_notebooks(self, user_id: Optional[str] = None) -> List[str]:
        """List all notebook IDs, optionally filtered by user"""
        pass
    
    @abstractmethod
    async def delete_notebook(self, notebook_id: str, user_id: str) -> None:
        """Delete a notebook from storage"""
        pass

