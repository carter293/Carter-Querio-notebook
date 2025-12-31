---
date: 2025-12-31T09:55:50Z
researcher: matthew
topic: "DynamoDB Implementation for Notebook Storage and Demo Notebook Provisioning"
tags: [research, codebase, storage, dynamodb, notebooks, demo-notebook, database-architecture]
status: complete
last_updated: 2025-12-31
last_updated_by: matthew
---

# Research: DynamoDB Implementation for Notebook Storage and Demo Notebook Provisioning

**Date**: 2025-12-31 09:55:50 GMT
**Researcher**: matthew
**Commit**: a1a8fd074551c8df6f2cd49ebddb7d2e3376a39d

## Research Question

1. How can we implement DynamoDB for storing and performing CRUD operations on notebooks?
2. How can we ensure every user gets a copy of the demo notebook (if not already implemented)?

## Summary

The notebook application currently uses **file-based JSON storage** in the `backend/notebooks/` directory. Demo notebooks are **already provisioned** for each user on first access via the `/notebooks` endpoint. To migrate to **DynamoDB**, we need to:

1. Design a DynamoDB schema with appropriate partition/sort keys and GSIs
2. Replace file-based storage operations with DynamoDB SDK calls
3. Implement async DynamoDB operations for all CRUD functions
4. Maintain the existing demo notebook provisioning logic (which already works)
5. Consider a hybrid approach with in-memory caching for active notebooks

**Important Context**: Previous research (Dec 30, 2025) recommended **AWS RDS PostgreSQL** with SQLModel for relational modeling, type safety, and complex queries. DynamoDB is a different architectural choice with trade-offs.

## Detailed Findings

### Current Storage Architecture

#### File-Based Storage Implementation
**Location**: `backend/storage.py`

The current system stores notebooks as JSON files:

```python
# Save operation
def save_notebook(notebook: Notebook) -> None:
    file_path = NOTEBOOKS_DIR / f"{notebook.id}.json"
    # Atomic write using temp file + os.replace
    with tempfile.NamedTemporaryFile(...) as f:
        json.dump(data, f, indent=2)
    os.replace(temp_path, file_path)

# Load operation
def load_notebook(notebook_id: str) -> Notebook:
    file_path = NOTEBOOKS_DIR / f"{notebook_id}.json"
    with open(file_path, 'r') as f:
        data = json.load(f)
    # Reconstruct Notebook object with cells, graph, etc.
```

**Key Features**:
- Atomic writes via temp file + `os.replace` (`storage.py:46-58`)
- Backward compatibility for legacy notebooks without `user_id` (`storage.py:88-97`)
- Directory structure: `notebooks/{notebook_id}.json`
- Rebuilds dependency graph after loading (`storage.py:109-110`)

#### Data Model
**Location**: `backend/models.py`

```python
@dataclass
class Notebook:
    id: str                           # UUID
    user_id: str                      # Clerk user ID
    name: Optional[str] = None
    db_conn_string: Optional[str] = None
    cells: List[Cell] = []
    graph: Graph = Graph()            # Not serialized (rebuilt)
    kernel: KernelState = KernelState()  # Not serialized
    revision: int = 0
    _lock: Lock = Lock()              # Not serialized

@dataclass
class Cell:
    id: str                           # UUID
    type: CellType                    # "python" | "sql"
    code: str
    status: CellStatus                # "idle" | "running" | "success" | "error"
    stdout: str = ""
    outputs: List[Output] = []
    error: Optional[str] = None
    reads: Set[str] = set()           # Variable dependencies
    writes: Set[str] = set()

@dataclass
class Output:
    mime_type: str                    # "image/png", "text/html", etc.
    data: Union[str, dict, list]      # base64 for images, dict for JSON
    metadata: Dict[str, Any] = {}
```

**Serialization Pattern** (`storage.py:16-42`):
- Flattens nested objects (cells, outputs) into nested dictionaries
- Converts sets to lists (`reads`, `writes`)
- Omits non-serializable fields (`graph`, `kernel`, `_lock`)
- Stores enums as string values

### Current Demo Notebook Provisioning

#### How It Works
**Location**: `backend/routes.py:175-217`

Demo notebooks **are already provisioned automatically**:

```python
@router.get("/notebooks", response_model=ListNotebooksResponse)
async def list_notebooks_endpoint(user_id: str = Depends(get_current_user_dependency)):
    # 1. Check for blank notebook
    blank_id = f"blank-{user_id}"
    if blank_id not in NOTEBOOKS:
        blank = Notebook(id=blank_id, user_id=user_id, cells=[...])
        NOTEBOOKS[blank_id] = blank
        save_notebook(blank)
    
    # 2. Check for demo notebook
    demo_id = f"demo-{user_id}"
    if demo_id not in NOTEBOOKS:
        demo = create_demo_notebook(user_id)
        demo.id = demo_id  # Override to user-specific ID
        NOTEBOOKS[demo_id] = demo
        save_notebook(demo)
    
    # 3. Return all user notebooks
    user_notebooks = [nb for nb in NOTEBOOKS.values() if nb.user_id == user_id]
    return ListNotebooksResponse(notebooks=[...])
```

**Trigger**: First time a user calls `GET /notebooks` (on app initialization)

**Demo Content** (`backend/demo_notebook.py:4-106`):
- 6 pre-populated cells demonstrating:
  - Variable dependencies (`x = 10`, `y = x + 5`)
  - Matplotlib plotting
  - Pandas DataFrame creation
  - Plotly interactive charts
  - Altair declarative visualizations
- All cells have pre-computed `reads`/`writes` for dependency tracking
- Dependency graph is rebuilt on creation

**Naming Convention**:
- Blank: `blank-{user_id}`
- Demo: `demo-{user_id}`

### CRUD Operations Pattern

All notebook mutations follow a consistent pattern:

1. **Acquire async lock** (`notebook._lock`)
2. **Perform mutation** (update cells, graph, etc.)
3. **Increment revision** (`notebook.revision += 1`)
4. **Persist to disk** (`save_notebook(notebook)`)

**Examples**:
- `notebook_operations.py:13-63` - Update cell code
- `notebook_operations.py:68-113` - Create new cell
- `notebook_operations.py:118-142` - Delete cell

**Concurrency Protection**:
- All cell operations use `async with notebook._lock`
- Optimistic locking via `expected_revision` parameter
- Revision conflicts raise `ValueError`

## DynamoDB Schema Design

### Recommended Table Structure

#### Primary Table: `notebooks`

**Partition Key**: `user_id` (String) - Clerk user ID
**Sort Key**: `notebook_id` (String) - UUID or special ID (e.g., `demo-{user_id}`)

**Attributes**:
```python
{
    "user_id": "user_37U0GVSi47Y4pucE7h9iZVesr4b",  # PK
    "notebook_id": "demo-user_37U0GVSi...",          # SK
    "name": "My Notebook",
    "db_conn_string": "postgresql://...",
    "revision": 42,
    "cells": [                                        # List of maps
        {
            "id": "cell-uuid-1",
            "type": "python",
            "code": "x = 10",
            "stdout": "",
            "outputs": [...],
            "error": null,
            "reads": ["x"],
            "writes": ["x"]
        },
        ...
    ],
    "created_at": "2025-12-31T09:00:00Z",            # ISO timestamp
    "updated_at": "2025-12-31T09:55:00Z",            # ISO timestamp
    "ttl": 1735776000                                 # Optional: Unix timestamp for expiration
}
```

**Global Secondary Index (GSI) 1**: `NotebookByIdIndex`
- **Partition Key**: `notebook_id` (String)
- **Purpose**: Direct notebook lookup by ID (for legacy compatibility)
- **Projection**: ALL

**Global Secondary Index (GSI) 2**: `NotebooksByUserCreatedIndex`
- **Partition Key**: `user_id` (String)
- **Sort Key**: `created_at` (String, ISO timestamp)
- **Purpose**: List user notebooks sorted by creation date
- **Projection**: KEYS_ONLY or INCLUDE `name`, `updated_at`

### Alternative: Separate Cells Table

For very large notebooks (>100 cells), consider a separate table:

#### Table: `notebook_cells`
**Partition Key**: `notebook_id` (String)
**Sort Key**: `position` (Number) - Cell order

This allows:
- Efficient cell pagination
- Partial notebook loading
- Finer-grained locking

**Trade-off**: More complex queries, requires transactions for consistency

### Access Patterns

1. **Get notebook by ID**: Query `notebooks` table with PK=`user_id`, SK=`notebook_id`
2. **List user notebooks**: Query `notebooks` table with PK=`user_id`
3. **Get notebook by ID only** (no user): Query GSI `NotebookByIdIndex` with PK=`notebook_id`
4. **Create notebook**: PutItem with `user_id` + `notebook_id`
5. **Update notebook**: UpdateItem with `SET cells = :cells, revision = revision + 1`
6. **Delete notebook**: DeleteItem with PK + SK

## Implementation Plan

### Phase 1: DynamoDB SDK Setup

1. **Install AWS SDK**:
   ```bash
   pip install boto3 aioboto3
   ```

2. **Configure credentials** (choose one):
   - IAM role (ECS task role) - **Recommended for production**
   - Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
   - AWS Secrets Manager (for local dev)

3. **Create DynamoDB table** (Terraform recommended):
   ```hcl
   resource "aws_dynamodb_table" "notebooks" {
     name           = "notebooks-${var.environment}"
     billing_mode   = "PAY_PER_REQUEST"  # Or PROVISIONED
     hash_key       = "user_id"
     range_key      = "notebook_id"
     
     attribute {
       name = "user_id"
       type = "S"
     }
     attribute {
       name = "notebook_id"
       type = "S"
     }
     
     global_secondary_index {
       name            = "NotebookByIdIndex"
       hash_key        = "notebook_id"
       projection_type = "ALL"
     }
     
     ttl {
       enabled        = true
       attribute_name = "ttl"
     }
   }
   ```

### Phase 2: Replace Storage Layer

**Create new file**: `backend/storage_dynamodb.py`

```python
import aioboto3
from typing import List, Optional
from models import Notebook, Cell, CellType, CellStatus, Output
import json
from datetime import datetime

class DynamoDBStorage:
    def __init__(self, table_name: str, region: str = "us-east-1"):
        self.table_name = table_name
        self.region = region
        self.session = aioboto3.Session()
    
    async def save_notebook(self, notebook: Notebook) -> None:
        """Save notebook to DynamoDB"""
        async with self.session.resource('dynamodb', region_name=self.region) as dynamodb:
            table = await dynamodb.Table(self.table_name)
            
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
                'updated_at': datetime.utcnow().isoformat() + 'Z',
                # Set created_at only if not exists (use ConditionExpression)
            }
            
            await table.put_item(Item=item)
    
    async def load_notebook(self, user_id: str, notebook_id: str) -> Optional[Notebook]:
        """Load notebook from DynamoDB"""
        async with self.session.resource('dynamodb', region_name=self.region) as dynamodb:
            table = await dynamodb.Table(self.table_name)
            
            response = await table.get_item(
                Key={'user_id': user_id, 'notebook_id': notebook_id}
            )
            
            if 'Item' not in response:
                return None
            
            data = response['Item']
            
            cells = [
                Cell(
                    id=cell_data['id'],
                    type=CellType(cell_data['type']),
                    code=cell_data['code'],
                    status=CellStatus.IDLE,
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
                for cell_data in data.get('cells', [])
            ]
            
            notebook = Notebook(
                id=data['notebook_id'],
                user_id=data['user_id'],
                name=data.get('name'),
                db_conn_string=data.get('db_conn_string'),
                cells=cells,
                revision=data.get('revision', 0)
            )
            
            from graph import rebuild_graph
            rebuild_graph(notebook)
            
            return notebook
    
    async def list_notebooks(self, user_id: str) -> List[str]:
        """List all notebook IDs for a user"""
        async with self.session.resource('dynamodb', region_name=self.region) as dynamodb:
            table = await dynamodb.Table(self.table_name)
            
            response = await table.query(
                KeyConditionExpression='user_id = :user_id',
                ExpressionAttributeValues={':user_id': user_id},
                ProjectionExpression='notebook_id'
            )
            
            return [item['notebook_id'] for item in response.get('Items', [])]
    
    async def delete_notebook(self, user_id: str, notebook_id: str) -> None:
        """Delete notebook from DynamoDB"""
        async with self.session.resource('dynamodb', region_name=self.region) as dynamodb:
            table = await dynamodb.Table(self.table_name)
            
            await table.delete_item(
                Key={'user_id': user_id, 'notebook_id': notebook_id}
            )
```

### Phase 3: Update Application Code

1. **Replace imports** in `routes.py`, `main.py`, `notebook_operations.py`, `scheduler.py`:
   ```python
   # OLD
   from storage import save_notebook, load_notebook, list_notebooks, delete_notebook
   
   # NEW
   from storage_dynamodb import DynamoDBStorage
   storage = DynamoDBStorage(table_name=os.getenv('DYNAMODB_TABLE_NAME'))
   ```

2. **Update function signatures** to `async`:
   ```python
   # OLD
   save_notebook(notebook)
   
   # NEW
   await storage.save_notebook(notebook)
   ```

3. **Update all callers** to use `await`:
   - `notebook_operations.py:60` - `await storage.save_notebook(notebook)`
   - `notebook_operations.py:110` - `await storage.save_notebook(notebook)`
   - `notebook_operations.py:140` - `await storage.save_notebook(notebook)`
   - `scheduler.py:150` - `await storage.save_notebook(notebook)`

4. **Update demo notebook provisioning** (`routes.py:175-217`):
   ```python
   # No changes needed! Logic remains the same:
   # 1. Check if demo-{user_id} exists in NOTEBOOKS dict
   # 2. If not, create via create_demo_notebook(user_id)
   # 3. Save with await storage.save_notebook(demo)
   ```

### Phase 4: Migration Script

**Create**: `backend/scripts/migrate_notebooks_to_dynamodb.py`

```python
import asyncio
from pathlib import Path
import json
from storage_dynamodb import DynamoDBStorage

async def migrate():
    storage = DynamoDBStorage(table_name='notebooks-production')
    notebooks_dir = Path('notebooks')
    
    for json_file in notebooks_dir.glob('*.json'):
        print(f"Migrating {json_file.name}...")
        
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        # Reconstruct Notebook object (same as load_notebook)
        # ... (cell reconstruction logic) ...
        
        # Save to DynamoDB
        await storage.save_notebook(notebook)
        
        print(f"✓ Migrated {notebook.id}")
    
    print("Migration complete!")

if __name__ == '__main__':
    asyncio.run(migrate())
```

### Phase 5: Testing & Validation

1. **Local testing** with DynamoDB Local:
   ```bash
   docker run -p 8000:8000 amazon/dynamodb-local
   ```

2. **Update tests** (`tests/test_storage.py`):
   - Mock DynamoDB calls using `moto` library
   - Test save/load/list/delete operations
   - Verify error handling for missing notebooks

3. **Integration tests**:
   - Run migration script on staging data
   - Verify all notebooks load correctly
   - Test CRUD operations through API
   - Verify demo notebook provisioning

## Demo Notebook Provisioning (Already Implemented)

**Current Status**: ✅ **Already working**

Every user automatically receives:
1. **Blank notebook** (`blank-{user_id}`) - Empty starting point
2. **Demo notebook** (`demo-{user_id}`) - 6 pre-populated cells

**Provisioning Logic** (`routes.py:175-217`):
- Triggered on first `GET /notebooks` request
- Checks in-memory `NOTEBOOKS` dict for existence
- Creates and saves if missing
- No changes needed for DynamoDB migration (just `await` storage calls)

**No Action Required**: The existing logic will continue to work with DynamoDB storage layer.

## Architecture Insights

### File-Based Storage Patterns

1. **Atomic Writes**: Uses temp file + `os.replace` for crash safety (`storage.py:46-58`)
2. **Backward Compatibility**: Gracefully handles missing `user_id` field (`storage.py:88-97`)
3. **Graph Reconstruction**: Always rebuilds dependency graph after loading (`storage.py:109-110`)
4. **Serialization**: Flattens nested objects, converts sets to lists
5. **In-Memory Cache**: `NOTEBOOKS` dict for fast access, persisted on every mutation

### Concurrency & Consistency

1. **Async Locks**: Every notebook has `_lock: Lock` for thread safety (`models.py:89`)
2. **Optimistic Locking**: Revision-based conflict detection (`notebook_operations.py:25-30`)
3. **Atomic Operations**: Lock → Mutate → Increment Revision → Persist pattern
4. **No Distributed Locks**: Current design assumes single-process (not multi-instance safe)

### Migration Considerations

**DynamoDB vs. RDS Trade-offs**:

| Aspect | DynamoDB | RDS (PostgreSQL) |
|--------|----------|------------------|
| **Schema** | Flexible (NoSQL) | Rigid (SQL, migrations) |
| **Relationships** | Denormalized | Normalized (foreign keys) |
| **Queries** | Key-based, GSIs | SQL (JOINs, aggregates) |
| **Scaling** | Automatic, serverless | Manual (instance size) |
| **Cost** | Pay-per-request or provisioned | Fixed instance cost |
| **Type Safety** | Manual validation | SQLModel + Pydantic |
| **Migrations** | Schema-less | Alembic required |
| **Complexity** | Lower (fewer concepts) | Higher (ORM, migrations) |
| **Latency** | Single-digit ms | <10ms (depends on instance) |
| **Multi-Region** | Global tables | Read replicas |

**Recommendation**: 
- **DynamoDB** if: Simple key-based access, high scale, serverless, minimal relational needs
- **RDS** if: Complex queries, relational integrity, type safety, SQL cell execution synergy

## Historical Context (from thoughts/)

### Database Architecture Research (2025-12-30)

**Document**: `thoughts/shared/research/2025-12-30-database-architecture-rds-migrations-type-safety.md`

**Key Recommendations**:
- **Migrate to AWS RDS PostgreSQL** (not DynamoDB)
- **Use SQLModel** (SQLAlchemy 2.0 + Pydantic v2) for type safety
- **Use Alembic** for schema migrations
- **Hybrid architecture**: In-memory cache + DB persistence (same as current file-based)
- **Schema design**: Separate tables for `users`, `notebooks`, `cells`, `cell_outputs`

**Rationale for RDS**:
- Demonstrates relational modeling and SQL expertise
- Better fit for notebook/cell/user relationships
- Aligns with existing SQL cell execution feature
- Enables complex queries (e.g., "notebooks with >10 cells", "users with SQL cells")
- Type safety via SQLModel

**Migration Path**:
1. Define SQLModel models for users, notebooks, cells
2. Set up Alembic for migrations
3. Create migration script to import JSON notebooks
4. Keep JSON files as backup initially
5. Remove file-based storage after validation

### Kernel Orchestration Research (2025-12-28)

**Document**: `thoughts/shared/research/2025-12-28-kernel-orchestration-architecture.md`

**DynamoDB Schema Examples** (for kernel management):
```python
# Session table
{
    "session_id": "uuid",         # PK
    "user_id": "clerk_user_id",   # GSI PK
    "notebook_id": "uuid",
    "kernel_task_arn": "ecs_task_arn",
    "status": "starting|running|stopped",
    "created_at": "2025-12-28T...",
    "ttl": 1735776000             # 1 hour TTL
}
```

**Relevance**: If implementing distributed kernels (ECS/Fargate), DynamoDB is better for session management due to:
- High write throughput for kernel state updates
- TTL for automatic session cleanup
- Serverless scaling

## Related Research

- `thoughts/shared/research/2025-12-30-database-architecture-rds-migrations-type-safety.md` - **Primary reference** for RDS migration
- `thoughts/shared/research/2025-12-28-kernel-orchestration-architecture.md` - DynamoDB for kernel session management
- `thoughts/shared/research/2025-12-27-loading-saving-named-notebooks-dropdown.md` - Notebook persistence requirements
- `thoughts/shared/plans/2025-12-27-reactive-notebook-enhancements.md` - Auto-save and persistence architecture

## Open Questions

1. **RDS vs. DynamoDB**: Should we use RDS (as recommended in Dec 30 research) or DynamoDB?
   - **Recommendation**: Start with **RDS** for reasons outlined in database-architecture research
   - Consider DynamoDB for kernel session management (separate concern)

2. **Single vs. Separate Cells Table**: Should cells be embedded in notebook items or in a separate table?
   - **Recommendation**: Start with **embedded cells** (simpler, fewer queries)
   - Move to separate table if notebooks regularly exceed 100 cells or 400KB

3. **Migration Strategy**: Big-bang cutover or gradual (dual-write)?
   - **Recommendation**: **Big-bang with downtime** (simpler, lower risk of data inconsistency)
   - Run migration script, verify, switch storage layer, deploy

4. **Distributed Locking**: How to handle concurrency in multi-instance deployment?
   - **Current**: Single-process async locks (not multi-instance safe)
   - **Options**: DynamoDB conditional writes, Redis locks, RDS row-level locks
   - **Recommendation**: Use **optimistic locking** (revision-based) + retry logic

5. **Demo Notebook Updates**: How to update demo notebook content for existing users?
   - **Current**: Demo created once on first access, never updated
   - **Options**: Version demo notebooks, allow "reset to latest demo"
   - **Recommendation**: Add `demo_version` field, show "Update Available" if version < latest

## Code References

- `backend/storage.py:13-58` - Current file-based save operation
- `backend/storage.py:60-112` - Current file-based load operation
- `backend/models.py:79-89` - Notebook data model
- `backend/models.py:34-43` - Cell data model
- `backend/demo_notebook.py:4-106` - Demo notebook creation logic
- `backend/routes.py:175-217` - Demo notebook provisioning logic
- `backend/notebook_operations.py:13-63` - Cell update with locking pattern
- `backend/notebook_operations.py:68-113` - Cell creation with locking pattern
- `backend/notebook_operations.py:118-142` - Cell deletion with locking pattern

## Next Steps

1. **Decision**: Choose between DynamoDB (this research) or RDS (Dec 30 research)
   - **Recommended**: Use **RDS** for notebook storage, DynamoDB for kernel sessions (if needed)

2. **If DynamoDB**:
   - Create Terraform config for `notebooks` table
   - Implement `storage_dynamodb.py` with async methods
   - Update all callers to use `await storage.*` pattern
   - Write migration script for existing JSON notebooks
   - Test locally with DynamoDB Local
   - Deploy to staging, run migration, validate
   - Deploy to production with maintenance window

3. **If RDS** (recommended):
   - Follow the implementation plan in `database-architecture-rds-migrations-type-safety.md`
   - Define SQLModel models for users, notebooks, cells
   - Set up Alembic and initial migration
   - Implement async storage layer with SQLAlchemy
   - Run migration script
   - Deploy with downtime window

4. **Demo Notebook Enhancements** (optional):
   - Add `demo_version` field to track demo content version
   - Implement "Reset to Latest Demo" feature
   - Update demo content (e.g., add new visualization libraries)

---

**Commit Hash**: a1a8fd074551c8df6f2cd49ebddb7d2e3376a39d
**Branch**: main
**Repository**: Carter-Querio-notebook

