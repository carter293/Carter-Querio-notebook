from pydantic import BaseModel
from typing import Optional, List


class CreateNotebookRequest(BaseModel):
    pass


class CreateNotebookResponse(BaseModel):
    notebook_id: str


class UpdateDbConnectionRequest(BaseModel):
    connection_string: str


class RenameNotebookRequest(BaseModel):
    name: str


class NotebookMetadataResponse(BaseModel):
    id: str
    name: str


class ListNotebooksResponse(BaseModel):
    notebooks: List[NotebookMetadataResponse]

