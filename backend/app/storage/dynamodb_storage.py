"""
Async DynamoDB storage layer for notebooks.
Provides single-digit millisecond latency for all operations.
"""
import aioboto3
import json
import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from decimal import Decimal
from app.models import Notebook, Cell, CellType, CellStatus, Output
from app.core import settings
from .base import StorageBackend
from botocore.exceptions import ClientError


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types from DynamoDB."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def convert_floats_to_decimal(obj: Any) -> Any:
    """
    Recursively convert all float values to Decimal for DynamoDB compatibility.
    DynamoDB does not support Python float types.
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_floats_to_decimal(item) for item in obj)
    return obj


def convert_decimal_to_float(obj: Any) -> Any:
    """
    Recursively convert all Decimal values back to float.
    Used when loading data from DynamoDB.
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimal_to_float(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_decimal_to_float(item) for item in obj)
    return obj


class DynamoDBStorage(StorageBackend):
    """Fast, serverless notebook storage using DynamoDB."""
    
    def __init__(self, table_name: str = None, region: str = None):
        self.table_name = table_name or settings.DYNAMODB_TABLE_NAME
        self.region = region or settings.AWS_REGION
        self.session = aioboto3.Session()
        
        if not self.table_name:
            raise ValueError("DYNAMODB_TABLE_NAME not configured")
    
    async def save_notebook(self, notebook: Notebook) -> None:
        """
        Save notebook to DynamoDB.
        
        Performance: <10ms for notebooks with <50 cells
        Item size limit: 400 KB (should fit ~100-200 cells)
        """
        async with self.session.resource('dynamodb', region_name=self.region) as dynamodb:
            table = await dynamodb.Table(self.table_name)
            
            # Serialize to DynamoDB format
            item = {
                'user_id': notebook.user_id,
                'notebook_id': notebook.id,
                'name': notebook.name,
                'db_conn_string': notebook.db_conn_string,
                'revision': notebook.revision,
                'cells': [
                    {
                        'id': cell.id,
                        'type': cell.type.value,
                        'code': cell.code,
                        'status': cell.status.value,
                        'stdout': cell.stdout,
                        'outputs': [
                            {
                                'mime_type': output.mime_type,
                                'data': output.data,
                                'metadata': output.metadata
                            }
                            for output in cell.outputs
                        ],
                        'error': cell.error,
                        'reads': list(cell.reads),
                        'writes': list(cell.writes)
                    }
                    for cell in notebook.cells
                ],
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            # Check if notebook exists to set created_at
            try:
                # Try to get existing item to check if created_at exists
                response = await table.get_item(
                    Key={
                        'user_id': notebook.user_id,
                        'notebook_id': notebook.id
                    },
                    ProjectionExpression='created_at'
                )
                
                if 'Item' in response and 'created_at' in response['Item']:
                    # Preserve existing created_at
                    item['created_at'] = response['Item']['created_at']
                else:
                    # Set created_at for new notebook
                    item['created_at'] = datetime.now(timezone.utc).isoformat()
            except Exception:
                # If any error, treat as new notebook
                item['created_at'] = datetime.now(timezone.utc).isoformat()
            
            # Convert all floats to Decimal for DynamoDB compatibility
            item = convert_floats_to_decimal(item)
            
            # Save item
            await table.put_item(Item=item)
    
    async def load_notebook(self, user_id: str, notebook_id: str) -> Optional[Notebook]:
        """
        Load notebook from DynamoDB.
        
        Performance: <5ms for GetItem operation
        """
        async with self.session.resource('dynamodb', region_name=self.region) as dynamodb:
            table = await dynamodb.Table(self.table_name)
            
            response = await table.get_item(
                Key={
                    'user_id': user_id,
                    'notebook_id': notebook_id
                },
                ConsistentRead=True  # Strong consistency for latest data
            )
            
            if 'Item' not in response:
                return None
            
            return self._deserialize_notebook(response['Item'])
    
    async def load_notebook_by_id(self, notebook_id: str) -> Optional[Notebook]:
        """
        Load notebook by ID only (uses GSI - slightly slower).
        
        Performance: <10ms for Query operation on GSI
        """
        async with self.session.resource('dynamodb', region_name=self.region) as dynamodb:
            table = await dynamodb.Table(self.table_name)
            
            response = await table.query(
                IndexName='NotebookByIdIndex',
                KeyConditionExpression='notebook_id = :notebook_id',
                ExpressionAttributeValues={
                    ':notebook_id': notebook_id
                }
            )
            
            if not response.get('Items'):
                return None
            
            return self._deserialize_notebook(response['Items'][0])
    
    async def list_notebooks(self, user_id: Optional[str] = None) -> List[str]:
        """
        List all notebooks for a user.
        
        Performance: <10ms for users with <100 notebooks
        Returns: List of notebook IDs
        """
        if not user_id:
            return []
        
        async with self.session.resource('dynamodb', region_name=self.region) as dynamodb:
            table = await dynamodb.Table(self.table_name)
            
            response = await table.query(
                KeyConditionExpression='user_id = :user_id',
                ExpressionAttributeValues={
                    ':user_id': user_id
                },
                ProjectionExpression='notebook_id, #n, updated_at',
                ExpressionAttributeNames={
                    '#n': 'name'  # 'name' is a reserved word
                }
            )
            
            return [item['notebook_id'] for item in response.get('Items', [])]
    
    async def delete_notebook(self, notebook_id: str, user_id: str) -> None:
        """
        Delete notebook from DynamoDB.
        
        Performance: <5ms for DeleteItem operation
        """
        async with self.session.resource('dynamodb', region_name=self.region) as dynamodb:
            table = await dynamodb.Table(self.table_name)
            
            await table.delete_item(
                Key={
                    'user_id': user_id,
                    'notebook_id': notebook_id
                }
            )
    
    def _deserialize_notebook(self, item: Dict[str, Any]) -> Notebook:
        """Convert DynamoDB item to Notebook object."""
        # Convert all Decimal values back to float
        item = convert_decimal_to_float(item)
        
        cells = [
            Cell(
                id=cell_data['id'],
                type=CellType(cell_data['type']),
                code=cell_data['code'],
                status=CellStatus.IDLE,  # Runtime state, not persisted
                stdout=cell_data.get('stdout', ''),
                outputs=[
                    Output(
                        mime_type=output_data['mime_type'],
                        data=output_data['data'],
                        metadata=output_data.get('metadata', {})
                    )
                    for output_data in cell_data.get('outputs', [])
                ],
                error=cell_data.get('error'),
                reads=set(cell_data.get('reads', [])),
                writes=set(cell_data.get('writes', []))
            )
            for cell_data in item.get('cells', [])
        ]
        
        notebook = Notebook(
            id=item['notebook_id'],
            user_id=item['user_id'],
            name=item.get('name'),
            db_conn_string=item.get('db_conn_string'),
            cells=cells,
            revision=int(item.get('revision', 0))
        )
        
        # Rebuild dependency graph
        from app.execution.dependencies import rebuild_graph
        rebuild_graph(notebook)
        
        return notebook

