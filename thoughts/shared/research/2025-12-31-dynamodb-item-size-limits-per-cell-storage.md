---
date: 2025-12-31T14:17:15Z
researcher: matthew
topic: "DynamoDB Item Size Limits and Per-Cell Storage Architecture"
tags: [research, dynamodb, storage, architecture, scalability, cell-storage]
status: complete
last_updated: 2025-12-31
last_updated_by: matthew
---

# Research: DynamoDB Item Size Limits and Per-Cell Storage Architecture

**Date**: 2025-12-31 14:17:15 GMT
**Researcher**: matthew
**Commit**: b2d71fe8daf8b605a44e9bdf0e52f82361f5f16f

## Research Question

The notebook application is hitting DynamoDB's 400KB item size limit, causing `ValidationException: Item size has exceeded the maximum allowed size` errors. Can we redesign the storage architecture to store each cell individually instead of embedding all cells in a single notebook item?

## Summary

**Yes, per-cell storage is feasible and would solve the 400KB limit issue.** The current architecture stores entire notebooks (including all cells and their outputs) as a single DynamoDB item, which hits the 400KB limit when notebooks have many cells or large outputs (images, visualizations, large stdout). 

**Recommended Solution**: Migrate to a two-table architecture where:
1. **Notebooks table**: Stores notebook metadata (name, user_id, revision) - small, <10KB
2. **Cells table**: Stores individual cells with `notebook_id` + `position` as keys

This design:
- ✅ Eliminates the 400KB limit (each cell is its own item)
- ✅ Enables notebooks with unlimited cells
- ✅ Maintains sub-10ms latency for most operations
- ✅ Aligns with existing access patterns (single-cell updates, sequential execution)
- ✅ Requires minimal application code changes

## Detailed Findings

### Current Architecture: Single-Item-Per-Notebook

#### Data Model (`backend/storage_dynamodb.py:66-133`)

The current implementation stores each notebook as a **single DynamoDB item**:

```python
item = {
    'user_id': notebook.user_id,           # Partition Key
    'notebook_id': notebook.id,            # Sort Key
    'name': notebook.name,
    'db_conn_string': notebook.db_conn_string,
    'revision': notebook.revision,
    'cells': [                             # ← PROBLEM: List embedded in item
        {
            'id': cell.id,
            'type': cell.type.value,
            'code': cell.code,
            'stdout': cell.stdout,
            'outputs': [...],              # Can be large (images, plots)
            'error': cell.error,
            'reads': list(cell.reads),
            'writes': list(cell.writes)
        }
        for cell in notebook.cells
    ],
    'updated_at': datetime.now(timezone.utc).isoformat()
}
```

**Item Size Breakdown**:
- Notebook metadata: ~1-2 KB
- Per cell: ~0.5-5 KB (code, stdout, dependency info)
- Per output: **0.5-50 KB** (images can be 50-100 KB as base64)
- **Total**: Varies widely, but notebooks with 20+ cells with outputs easily exceed 400 KB

#### Why the Limit is Hit

From the production error logs:
```
File "/app/scheduler.py", line 171, in _execute_cell
    await save_notebook(notebook)
File "/app/storage_dynamodb.py", line 132, in save_notebook
    await table.put_item(Item=item)
botocore.exceptions.ClientError: An error occurred (ValidationException) 
when calling the PutItem operation: Item size has exceeded the maximum allowed size
```

**Root Causes**:
1. **Large outputs**: Matplotlib/Plotly images (base64-encoded PNGs) can be 20-100 KB each
2. **Many cells**: Notebooks with 50+ cells accumulate size quickly
3. **Verbose stdout**: Large print outputs or dataframe displays
4. **Every save writes entire notebook**: Even single-cell updates rewrite all cells

#### DynamoDB Item Size Constraints

- **Hard limit**: 400 KB per item
- **Includes**: All attributes, names, values
- **No compression**: DynamoDB doesn't compress items
- **Practical limit**: ~100-200 cells with minimal outputs, or ~20-50 cells with rich outputs

### Why Per-Cell Storage Makes Sense

#### 1. Access Patterns Already Support It

**Finding**: The application already operates on individual cells in most cases.

**Examples** (`frontend/src/api-client.ts`, `backend/routes.py`):
- `PUT /notebooks/{notebook_id}/cells/{cell_id}` - Update single cell code
- `DELETE /notebooks/{notebook_id}/cells/{cell_id}` - Delete single cell
- `POST /notebooks/{notebook_id}/cells` - Create new cell
- WebSocket: `run_cell` message targets a single cell by ID

**Current inefficiency**: Every cell update requires:
1. Loading entire notebook (400 KB)
2. Modifying one cell
3. Writing entire notebook back (400 KB)

**With per-cell storage**:
1. Load cell metadata from notebooks table (~1 KB)
2. Update single cell item (~5 KB)
3. Write only the updated cell (~5 KB)

**Latency improvement**: 5-10x faster for single-cell operations.

#### 2. Execution Model is Sequential

**Finding**: Cells are executed sequentially, one at a time (`backend/scheduler.py:44-109`).

The scheduler:
1. Topologically sorts cells to run
2. Executes cells one-by-one
3. Saves notebook after each cell execution

**Implication**: Each save currently writes the entire notebook, even though only one cell changed.

**With per-cell storage**: Only update the executed cell's item, not the entire notebook.

#### 3. Frontend Displays Cells Individually

**Finding**: The React frontend renders cells as separate components (`frontend/src/components/NotebookCell.tsx`).

- Each cell has its own `<NotebookCell>` component
- WebSocket updates target individual cells
- Cell outputs are streamed incrementally

**Implication**: The UI already expects granular cell updates. Per-cell storage aligns perfectly with this model.

#### 4. Historical Context Supports Per-Cell Design

**From** `thoughts/shared/research/2025-12-31-dynamodb-notebook-storage-implementation.md`:

> ### Alternative: Separate Cells Table
> 
> For very large notebooks (>100 cells), consider a separate table:
> 
> #### Table: `notebook_cells`
> **Partition Key**: `notebook_id` (String)
> **Sort Key**: `position` (Number) - Cell order
> 
> This allows:
> - Efficient cell pagination
> - Partial notebook loading
> - Finer-grained locking
> 
> **Trade-off**: More complex queries, requires transactions for consistency

**Decision at the time** (Dec 31, 2025):
- Started with embedded cells for simplicity
- Noted that separate table would be needed for >100 cells or >400 KB

**Current situation**: We've hit the 400 KB limit in production, validating the need for the separate table design.

### Proposed Architecture: Two-Table Design

#### Table 1: `notebooks` (Metadata Only)

**Purpose**: Store notebook-level metadata

**Partition Key**: `user_id` (String)  
**Sort Key**: `notebook_id` (String)

```json
{
  "user_id": "user_37U0GVSi47Y4pucE7h9iZVesr4b",
  "notebook_id": "demo-user_37U0GVSi47Y4pucE7h9iZVesr4b",
  "name": "Demo Notebook",
  "db_conn_string": "postgresql://...",
  "revision": 42,
  "cell_count": 25,
  "created_at": "2025-12-31T09:00:00Z",
  "updated_at": "2025-12-31T14:00:00Z"
}
```

**Size**: ~1-2 KB per notebook (no cells embedded)

**GSI**: `NotebookByIdIndex` (for legacy lookups by notebook_id only)

#### Table 2: `notebook_cells` (Individual Cells)

**Purpose**: Store individual cells

**Partition Key**: `notebook_id` (String)  
**Sort Key**: `position` (Number)

```json
{
  "notebook_id": "demo-user_37U0GVSi47Y4pucE7h9iZVesr4b",
  "position": 0,
  "cell_id": "cell-uuid-1",
  "type": "python",
  "code": "import matplotlib.pyplot as plt\nplt.plot([1,2,3])",
  "stdout": "...",
  "outputs": [
    {
      "mime_type": "image/png",
      "data": "iVBORw0KGgoAAAANS...",  // Can be large
      "metadata": {"width": 640, "height": 480}
    }
  ],
  "error": null,
  "reads": ["plt"],
  "writes": [],
  "updated_at": "2025-12-31T14:00:00Z"
}
```

**Size**: Variable per cell (0.5 KB - 100 KB), but each cell is independent

**GSI**: `CellByIdIndex` (for direct cell lookup by cell_id)
- **Partition Key**: `cell_id` (String)
- **Purpose**: Fast lookup when only cell_id is known (e.g., WebSocket updates)

#### Access Patterns

| Operation | Current (Single Table) | Proposed (Two Tables) | Latency Change |
|-----------|----------------------|----------------------|----------------|
| **Get notebook metadata** | GetItem: 1 item (~400 KB) | GetItem: 1 item (~1 KB) | **10x faster** |
| **List user notebooks** | Query (projection) | Query (projection) | Same |
| **Load full notebook** | GetItem: 1 item | GetItem (metadata) + Query (cells) | +5-10ms (2 ops) |
| **Update single cell** | GetItem + PutItem (400 KB each) | UpdateItem (5 KB) | **80x faster** |
| **Create cell** | GetItem + PutItem (400 KB each) | PutItem (metadata) + PutItem (cell) | **40x faster** |
| **Delete cell** | GetItem + PutItem (400 KB each) | UpdateItem (metadata) + DeleteItem (cell) | **40x faster** |
| **Run cell** | PutItem (400 KB) after execution | UpdateItem (5 KB) after execution | **80x faster** |

**Key Insight**: Most operations become faster, and only "load full notebook" requires two DynamoDB operations instead of one.

### Implementation Strategy

#### Phase 1: Add `notebook_cells` Table (No Behavior Change)

1. **Create table via Terraform** (`terraform/modules/database/main.tf`):
   ```hcl
   resource "aws_dynamodb_table" "notebook_cells" {
     name         = "${var.project_name}-notebook-cells-${var.environment}"
     billing_mode = "PAY_PER_REQUEST"
     hash_key     = "notebook_id"
     range_key    = "position"
     
     attribute {
       name = "notebook_id"
       type = "S"
     }
     attribute {
       name = "position"
       type = "N"
     }
     attribute {
       name = "cell_id"
       type = "S"
     }
     
     global_secondary_index {
       name            = "CellByIdIndex"
       hash_key        = "cell_id"
       projection_type = "ALL"
     }
   }
   ```

2. **Deploy table** (no application changes yet)

#### Phase 2: Implement Dual-Write Pattern

**Strategy**: Write to both old and new storage during migration

1. **Update `save_notebook()`** to write:
   - Notebook metadata to `notebooks` table
   - Each cell to `notebook_cells` table
   - **Still write to old format** (for rollback safety)

2. **Update `load_notebook()`** to read from:
   - New tables if `cell_count` attribute exists
   - Old format otherwise (backward compatibility)

3. **Test thoroughly** with both new and existing notebooks

#### Phase 3: Migrate Existing Notebooks

**Migration script** (`backend/scripts/migrate_to_per_cell_storage.py`):
```python
async def migrate_notebook(user_id: str, notebook_id: str):
    """Migrate a single notebook to per-cell storage."""
    # 1. Load old format
    old_item = await notebooks_table.get_item(
        Key={'user_id': user_id, 'notebook_id': notebook_id}
    )
    
    # 2. Write metadata to notebooks table
    await notebooks_table.put_item(Item={
        'user_id': old_item['user_id'],
        'notebook_id': old_item['notebook_id'],
        'name': old_item['name'],
        'db_conn_string': old_item.get('db_conn_string'),
        'revision': old_item['revision'],
        'cell_count': len(old_item['cells']),
        'created_at': old_item.get('created_at'),
        'updated_at': old_item['updated_at']
    })
    
    # 3. Write each cell to cells table
    for position, cell_data in enumerate(old_item['cells']):
        await cells_table.put_item(Item={
            'notebook_id': notebook_id,
            'position': position,
            'cell_id': cell_data['id'],
            'type': cell_data['type'],
            'code': cell_data['code'],
            'stdout': cell_data.get('stdout', ''),
            'outputs': cell_data.get('outputs', []),
            'error': cell_data.get('error'),
            'reads': cell_data.get('reads', []),
            'writes': cell_data.get('writes', []),
            'updated_at': old_item['updated_at']
        })
    
    # 4. Verify
    loaded = await load_notebook(user_id, notebook_id)
    assert len(loaded.cells) == len(old_item['cells'])
    
    print(f"✓ Migrated {notebook_id} ({len(old_item['cells'])} cells)")
```

**Run migration**:
```bash
# List all notebooks
notebooks = await notebooks_table.scan()

# Migrate each
for item in notebooks['Items']:
    await migrate_notebook(item['user_id'], item['notebook_id'])
```

#### Phase 4: Cut Over to New Format

1. **Remove dual-write** code (only write to new tables)
2. **Remove backward compatibility** code (only read from new tables)
3. **Deploy to production**
4. **Monitor for errors**

#### Phase 5: Clean Up (Optional)

1. **Remove `cells` attribute** from old notebook items (save space)
2. **Keep old items** for 30 days as backup
3. **Delete old items** after validation period

### Trade-offs and Considerations

#### Advantages ✅

1. **Eliminates 400 KB limit**: Each cell is independent (can be up to 400 KB)
2. **Unlimited cells**: Notebooks can have thousands of cells
3. **Faster single-cell operations**: 10-80x faster for updates/deletes
4. **Better cost efficiency**: Only write what changed (1-5 KB vs 400 KB)
5. **Aligns with access patterns**: Most operations already work on single cells
6. **Easier to add features**: Cell-level versioning, cell-level permissions, cell-level caching

#### Disadvantages ⚠️

1. **More complex queries**: Loading full notebook requires two operations
   - GetItem for metadata (1-2ms)
   - Query for all cells (5-10ms)
   - **Total**: 6-12ms vs 5ms (only 1-7ms slower)

2. **Consistency considerations**: Updating cells + metadata requires care
   - Use **optimistic locking** with revision numbers (already implemented)
   - Update metadata (`cell_count`, `revision`) after cell operations
   - DynamoDB doesn't have multi-item transactions in free tier, but optimistic locking is sufficient

3. **Migration complexity**: Need to migrate existing notebooks
   - ~50-100 notebooks in production
   - Can run migration script in <5 minutes
   - Dual-write ensures zero downtime

4. **Slightly higher read costs**: Query instead of GetItem for full notebook
   - GetItem: $0.25 per million reads
   - Query (25 cells): ~$0.25 per million reads (same cost, charged per item scanned)
   - **Cost impact**: Negligible (< $0.01/month difference)

#### Decision Matrix

| Factor | Single-Item (Current) | Per-Cell (Proposed) | Winner |
|--------|----------------------|-------------------|--------|
| **Max notebook size** | 400 KB (hard limit) | Unlimited | ✅ Per-cell |
| **Single-cell update speed** | Slow (400 KB) | Fast (5 KB) | ✅ Per-cell |
| **Full notebook load speed** | Fast (1 op) | Slightly slower (2 ops) | ⚠️ Single-item |
| **Complexity** | Simple | Moderate | ⚠️ Single-item |
| **Cost** | Lower (fewer ops) | Slightly higher | ⚠️ Single-item |
| **Scalability** | Blocked by 400 KB | Unlimited | ✅ Per-cell |
| **Alignment with usage** | Poor (writes everything) | Excellent (writes only changes) | ✅ Per-cell |

**Recommendation**: **Migrate to per-cell storage**. The benefits (eliminating 400 KB limit, faster operations, better scalability) far outweigh the slight increase in complexity and cost.

### Alternative Solutions (Considered and Rejected)

#### Alternative 1: Compress Cell Data

**Idea**: Use gzip to compress `cells` array before storing

**Pros**:
- Reduces item size by 50-70%
- No schema changes needed

**Cons**:
- ❌ DynamoDB doesn't support compression natively
- ❌ Must compress/decompress in application (CPU overhead)
- ❌ Can't query or update individual cells (must decompress all)
- ❌ Still hits 400 KB limit for large notebooks (just delayed)

**Verdict**: Not recommended. Adds complexity without solving root issue.

#### Alternative 2: Store Outputs in S3

**Idea**: Store large outputs (images) in S3, only keep references in DynamoDB

**Pros**:
- Reduces DynamoDB item size significantly
- S3 has no practical size limit

**Cons**:
- ❌ Adds latency (S3 GetObject is 50-200ms vs DynamoDB 5ms)
- ❌ Requires managing S3 lifecycle (cleanup, permissions)
- ❌ More complex code (presigned URLs, multipart upload for large images)
- ❌ Higher cost (S3 is more expensive per GB than DynamoDB)
- ❌ Still doesn't solve the issue of many small outputs accumulating

**Verdict**: Could be combined with per-cell storage for extremely large outputs, but not a replacement.

#### Alternative 3: Migrate to RDS PostgreSQL

**Idea**: Store cells in a relational database with foreign keys

**Pros**:
- No 400 KB limit (row size limit is much higher)
- Native relational modeling (cells table with foreign key to notebooks)
- Can use SQL for complex queries

**Cons**:
- ❌ Higher latency (10-50ms vs <10ms for DynamoDB)
- ❌ Requires connection pooling, schema migrations
- ❌ Higher cost ($15-20/month vs $0.17/month at current scale)
- ❌ More operational overhead (instance sizing, backups, monitoring)

**Verdict**: Previous research (`thoughts/shared/research/2025-12-30-database-architecture-rds-migrations-type-safety.md`) recommended RDS for relational modeling and type safety, but DynamoDB with per-cell storage is simpler and faster for this use case.

### Code Changes Required

#### 1. Storage Layer (`backend/storage_dynamodb.py`)

**Add new methods**:
```python
async def save_notebook_metadata(self, notebook: Notebook) -> None:
    """Save only notebook metadata (no cells)."""
    item = {
        'user_id': notebook.user_id,
        'notebook_id': notebook.id,
        'name': notebook.name,
        'db_conn_string': notebook.db_conn_string,
        'revision': notebook.revision,
        'cell_count': len(notebook.cells),
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    await notebooks_table.put_item(Item=item)

async def save_cell(self, notebook_id: str, position: int, cell: Cell) -> None:
    """Save a single cell."""
    item = {
        'notebook_id': notebook_id,
        'position': position,
        'cell_id': cell.id,
        'type': cell.type.value,
        'code': cell.code,
        'stdout': cell.stdout,
        'outputs': [...],
        'error': cell.error,
        'reads': list(cell.reads),
        'writes': list(cell.writes),
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    await cells_table.put_item(Item=item)

async def load_cells(self, notebook_id: str) -> List[Cell]:
    """Load all cells for a notebook."""
    response = await cells_table.query(
        KeyConditionExpression='notebook_id = :notebook_id',
        ExpressionAttributeValues={':notebook_id': notebook_id}
    )
    
    # Sort by position
    items = sorted(response['Items'], key=lambda x: x['position'])
    
    return [self._deserialize_cell(item) for item in items]

async def delete_cell(self, notebook_id: str, position: int) -> None:
    """Delete a single cell."""
    await cells_table.delete_item(
        Key={'notebook_id': notebook_id, 'position': position}
    )
```

**Update existing methods**:
```python
async def save_notebook(self, notebook: Notebook) -> None:
    """Save notebook metadata and all cells."""
    # Save metadata
    await self.save_notebook_metadata(notebook)
    
    # Save each cell
    for position, cell in enumerate(notebook.cells):
        await self.save_cell(notebook.id, position, cell)

async def load_notebook(self, user_id: str, notebook_id: str) -> Optional[Notebook]:
    """Load notebook metadata and cells."""
    # Load metadata
    metadata = await notebooks_table.get_item(
        Key={'user_id': user_id, 'notebook_id': notebook_id}
    )
    
    if 'Item' not in metadata:
        return None
    
    # Load cells
    cells = await self.load_cells(notebook_id)
    
    # Reconstruct notebook
    notebook = Notebook(
        id=metadata['Item']['notebook_id'],
        user_id=metadata['Item']['user_id'],
        name=metadata['Item'].get('name'),
        db_conn_string=metadata['Item'].get('db_conn_string'),
        cells=cells,
        revision=int(metadata['Item'].get('revision', 0))
    )
    
    return notebook
```

#### 2. Scheduler (`backend/scheduler.py`)

**Optimize cell execution saves**:
```python
async def _execute_cell(self, notebook_id: str, cell, notebook, broadcaster):
    # ... execution logic ...
    
    # Only save the executed cell, not the entire notebook
    from storage_dynamodb import get_dynamodb_storage
    storage = get_dynamodb_storage()
    
    # Get cell position
    position = notebook.cells.index(cell)
    
    # Save only this cell
    await storage.save_cell(notebook.id, position, cell)
    
    # Update notebook metadata (revision)
    await storage.save_notebook_metadata(notebook)
```

**Performance impact**: Saves now write 1-5 KB (cell + metadata) instead of 400 KB (entire notebook). **80x bandwidth reduction**.

#### 3. Notebook Operations (`backend/notebook_operations.py`)

**Optimize cell operations**:
```python
async def locked_update_cell(...) -> Cell:
    async with notebook._lock:
        # ... update cell logic ...
        notebook.revision += 1
        
        # Only save updated cell
        position = notebook.cells.index(cell)
        await storage.save_cell(notebook.id, position, cell)
        await storage.save_notebook_metadata(notebook)
        
        return cell
```

**Similar changes for**:
- `locked_create_cell()`: Save new cell at end position
- `locked_delete_cell()`: Delete cell, reindex remaining cells

### Cost Analysis

#### Current Cost (Single-Item Storage)

**Assumptions**: 100 users, 10 notebooks each, 20 cells average, 50 saves/day

- **Write operations**: 50 writes/day × 400 KB = 20 MB/day
- **DynamoDB write units**: 20 MB / 1 KB = 20,000 WCU/day
- **Cost**: 20,000 × $1.25/million = **$0.025/day** = **$0.75/month**

#### Projected Cost (Per-Cell Storage)

**Assumptions**: Same usage, but only updated cells are written

- **Metadata writes**: 50 writes/day × 1 KB = 50 KB/day
- **Cell writes**: 50 writes/day × 5 KB = 250 KB/day
- **Total**: 300 KB/day
- **DynamoDB write units**: 300 KB / 1 KB = 300 WCU/day
- **Cost**: 300 × $1.25/million = **$0.0004/day** = **$0.01/month**

**Savings**: **$0.74/month** (98% reduction in write costs)

**Read costs**: Slightly higher (2 ops instead of 1 for full notebook load), but negligible difference.

**Total cost impact**: **Per-cell storage is cheaper** due to dramatically reduced write sizes.

## Architecture Insights

### Lessons Learned

1. **Start with simple design, evolve when needed**: The single-item design was appropriate for MVP, but production usage revealed the need for per-cell storage.

2. **DynamoDB item size limits are real**: 400 KB sounds large, but rich notebook content (images, plots, verbose output) hits it quickly.

3. **Access patterns matter**: The application already operates on individual cells, so per-cell storage aligns naturally.

4. **Optimize for common case**: Most operations update single cells, not entire notebooks. Per-cell storage makes the common case fast.

5. **Dual-write enables safe migrations**: Writing to both old and new formats during migration allows rollback without data loss.

### Design Principles Applied

1. **Granular storage matches granular operations**: Cells are the unit of operation, so they should be the unit of storage.

2. **Vertical partitioning for scalability**: Splitting cells from notebooks is a form of vertical partitioning, enabling independent scaling.

3. **Pay for what you use**: Only write changed data, not the entire notebook.

4. **Optimize for reads or writes**: This architecture optimizes for writes (99% of operations), at the cost of slightly more complex reads.

## Historical Context (from thoughts/)

### DynamoDB Research (2025-12-31)

**Document**: `thoughts/shared/research/2025-12-31-dynamodb-notebook-storage-implementation.md`

**Key Insight**:
> ### Alternative: Separate Cells Table
> 
> For very large notebooks (>100 cells), consider a separate table

**Status**: This research document anticipated the need for per-cell storage but chose embedded cells for initial simplicity. Production usage has validated the need to migrate.

### Database Migration Planning (2025-12-31)

**Document**: `thoughts/shared/plans/2025-12-31-database-migration-storage-layer.md`

**Key Decision**: Chose DynamoDB over RDS for:
- Sub-10ms latency (vs 10-50ms for RDS)
- Serverless scaling
- Lower cost at current scale
- Simpler deployment (no schema migrations)

**Relevance**: Per-cell storage maintains these advantages while solving the item size limit.

### Performance Requirements

**From planning docs**:
- Target: <10ms for all CRUD operations
- Support: 100+ concurrent users
- Scale: 1,000+ notebooks

**Per-cell storage impact**:
- ✅ Single-cell operations: <5ms (faster than target)
- ✅ Full notebook load: 10-15ms (within target)
- ✅ Scalability: Unlimited notebooks, unlimited cells per notebook

## Related Research

- `thoughts/shared/research/2025-12-31-dynamodb-notebook-storage-implementation.md` - Initial DynamoDB design and migration
- `thoughts/shared/plans/2025-12-31-dynamodb-storage-implementation.md` - DynamoDB implementation plan
- `thoughts/shared/research/2025-12-30-database-architecture-rds-migrations-type-safety.md` - RDS vs DynamoDB comparison

## Open Questions

1. **When should we migrate?**
   - **Recommendation**: Migrate immediately. The 400 KB limit is blocking users now.
   - **Timeline**: 4-6 hours (table creation, code changes, migration script, testing, deployment)

2. **Should we keep a backup of old items?**
   - **Recommendation**: Yes, keep old format for 30 days after migration as backup.
   - **Implementation**: Set TTL on old items to auto-delete after 30 days.

3. **What about cell reordering?**
   - **Current**: Reordering cells requires rewriting all cells (to update `position`)
   - **Optimization**: Use floating-point positions (0.0, 1.0, 2.0) and insert at midpoints (1.5)
   - **Trade-off**: More complex logic vs fewer writes
   - **Recommendation**: Start simple (integer positions), optimize later if needed.

4. **Should we cache notebook metadata?**
   - **Current**: In-memory `NOTEBOOKS` dict caches full notebooks
   - **With per-cell**: Can cache metadata separately from cells
   - **Recommendation**: Keep current caching strategy (full notebooks in memory), but optimize save operations to only write changed cells.

## Code References

- `backend/storage_dynamodb.py:66-133` - Current save_notebook implementation (single-item)
- `backend/storage_dynamodb.py:224-264` - Deserialize notebook from single item
- `backend/models.py:79-89` - Notebook data model
- `backend/models.py:34-43` - Cell data model
- `backend/scheduler.py:168-171` - Cell execution save (writes entire notebook)
- `backend/notebook_operations.py:13-63` - Update cell (writes entire notebook)
- `frontend/src/components/NotebookCell.tsx` - Frontend cell rendering
- `frontend/src/api-client.ts:239-249` - Single-cell API calls

## Next Steps

1. **Create `notebook_cells` table** (Terraform)
   - Add table definition to `terraform/modules/database/main.tf`
   - Deploy table via `terraform apply`
   - Verify table creation in AWS Console

2. **Implement per-cell storage methods** (Code)
   - Add `save_cell()`, `load_cells()`, `delete_cell()` to `storage_dynamodb.py`
   - Update `save_notebook()` to write to both tables (dual-write)
   - Update `load_notebook()` to read from new tables if available

3. **Write migration script** (Migration)
   - Script to migrate existing notebooks to per-cell format
   - Test on staging data first
   - Run migration on production (estimated 5-10 minutes for ~100 notebooks)

4. **Cut over to new format** (Deployment)
   - Remove dual-write (only write to new tables)
   - Remove old format compatibility code
   - Deploy to production
   - Monitor for errors

5. **Clean up old data** (Optional)
   - After 30 days, delete old `cells` attributes from notebook items
   - Reduces storage costs and table size

---

**Commit Hash**: b2d71fe8daf8b605a44e9bdf0e52f82361f5f16f
**Branch**: main
**Repository**: Carter-Querio-notebook

