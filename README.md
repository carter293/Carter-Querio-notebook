# Reactive Notebook

Reactive notebook with dependency-driven cell execution. Built with FastAPI, React, and deployed on AWS.

## Architecture

**Backend:** FastAPI + AsyncIO  
**Frontend:** React + TypeScript + Vite  
**Auth:** Clerk (JWT with JWKS verification)  
**Storage:** DynamoDB  
**Infrastructure:** AWS ECS Fargate, ALB, CloudFront, S3  
**IaC:** Terraform with modular structure

### Core Components

- **AST Parser** (`ast_parser.py`) - Extracts reads/writes from Python, templates from SQL
- **Dependency Graph** (`graph.py`) - DAG construction, topological sort, cycle detection
- **Executor** (`executor.py`) - Python/SQL execution with output capture
- **Scheduler** (`scheduler.py`) - Reactive execution queue with concurrency control
- **WebSocket Broadcaster** (`websocket.py`) - Real-time cell updates to all clients

### Execution Model

1. User edits cell → AST parser extracts dependencies
2. Graph rebuilt with new edges (writer → reader)
3. Cell queued for execution → all dependents found via DFS
4. Topological sort ensures correct execution order
5. Results broadcasted via WebSocket

## Quick Start

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
python main.py  # runs on :8000

# Frontend
cd frontend
npm install
npm run dev  # runs on :5173
```

### Environment Variables (Local Dev)

```bash
# Backend
export ANTHROPIC_API_KEY=sk-ant-api03...
export CLERK_FRONTEND_API=modern-cricket-32.clerk.accounts.dev

# Frontend
export export VITE_CLERK_PUBLISHABLE_KEY=pk_test_b31aAd...
```

## Deployment

### Required Environment Variables

```bash
export TF_VAR_clerk_frontend_api=clerk.matthewcarter.info
export TF_VAR_anthropic_api_key=sk-ant-api03...
export CLERK_PUBLISHABLE_KEY=pk_live_...
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
```

### Deploy

```bash
# 1. Update infrastructure
cd terraform && terraform apply -var-file=production.tfvars

# 2. Deploy backend
cd backend && ./scripts/deploy.sh

# 3. Deploy frontend  
cd frontend && ./deploy.sh
```

## API

### HTTP Endpoints

- `POST /api/notebooks` - Create notebook
- `GET /api/notebooks` - List user's notebooks
- `GET /api/notebooks/{id}` - Get notebook
- `POST /api/notebooks/{id}/cells` - Create cell
- `PUT /api/notebooks/{id}/cells/{cell_id}` - Update cell code
- `DELETE /api/notebooks/{id}/cells/{cell_id}` - Delete cell

### WebSocket

- `WS /ws/notebooks/{id}` - Real-time updates

**Client → Server:**
```json
{"type": "authenticate", "token": "..."}
{"type": "run_cell", "cellId": "..."}
```

**Server → Client:**
```json
{"type": "cell_status", "cellId": "...", "status": "running"}
{"type": "cell_stdout", "cellId": "...", "data": "..."}
{"type": "cell_output", "cellId": "...", "output": {...}}
{"type": "cell_error", "cellId": "...", "error": "..."}
```

## Features

- **Reactive Execution** - Cells auto-rerun when dependencies change
- **Dependency Tracking** - AST-based static analysis (Python) and template parsing (SQL)
- **SQL Support** - Template variables: `SELECT * FROM users WHERE id = {user_id}`
- **Real-time Updates** - WebSocket broadcasting for all cell events
- **Cycle Detection** - Automatic detection and reporting of circular dependencies
- **Multi-user** - Per-user notebooks with Clerk authentication
- **Persistent Storage** - DynamoDB backend (falls back to file storage in dev)

## Infrastructure

Modular Terraform configuration under `terraform/modules/`:

- **networking** - VPC, subnets, NAT, routing
- **security** - Security groups, IAM roles, CloudWatch logs
- **storage** - ECR (Docker), S3 (frontend), DynamoDB (notebooks)
- **compute** - ECS Fargate cluster, ALB, task definitions
- **cdn** - CloudFront distribution with custom domain support
- **database** - DynamoDB table with CloudWatch alarms

### AWS Resources

- **Compute:** ECS Fargate (backend), S3 + CloudFront (frontend)
- **Networking:** VPC with public/private subnets, NAT gateway, ALB
- **Storage:** DynamoDB (notebooks), ECR (Docker images), S3 (static assets)
- **Security:** IAM roles, security groups, ACM certificates
- **Monitoring:** CloudWatch logs, DynamoDB alarms

## Testing

```bash
# Backend tests
cd backend
pytest tests/ -v

# Core tests
pytest tests/test_ast_parser.py tests/test_graph.py -v
```

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI app + Clerk JWT verification
│   ├── models.py            # Pydantic models (Notebook, Cell, Graph)
│   ├── ast_parser.py        # Dependency extraction
│   ├── graph.py             # DAG + topological sort
│   ├── executor.py          # Python/SQL execution
│   ├── scheduler.py         # Reactive execution queue
│   ├── websocket.py         # Real-time broadcaster
│   ├── routes.py            # HTTP + WebSocket endpoints
│   ├── storage.py           # File-based storage
│   ├── storage_dynamodb.py  # DynamoDB storage
│   └── scripts/
│       ├── deploy.sh        # Build + push to ECR + update ECS
│       └── update-service.sh
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── NotebookApp.tsx    # Main notebook UI
│   │   │   ├── NotebookCell.tsx   # Cell component
│   │   │   └── ChatPanel.tsx      # LLM chat integration
│   │   ├── api-client.ts          # HTTP client with auth
│   │   └── useNotebookWebSocket.ts # WebSocket hook
│   └── deploy.sh            # Build + upload to S3 + invalidate CloudFront
├── terraform/
│   ├── main.tf              # Root module orchestration
│   ├── variables.tf         # Input variables
│   ├── production.tfvars    # Production config
│   └── modules/             # Modular infrastructure
└── tests/
    └── integration-test.sh  # End-to-end test script
```

## Technical Details

### Dependency Extraction

**Python cells:**
```python
x = 10           # writes: {x}
y = x * 2        # reads: {x}, writes: {y}
z = y + x        # reads: {x, y}, writes: {z}
```
Uses Python AST walker to identify assignments (writes) and name references (reads).

**SQL cells:**
```sql
SELECT * FROM users WHERE id = {user_id}
-- reads: {user_id}, writes: {}
```
Regex-based template variable extraction. Variables substituted from kernel globals before execution.

### Concurrency

- Per-notebook asyncio lock prevents race conditions during execution
- Scheduler queues cell runs, drains queue atomically
- Execution is sequential per notebook (topological order), but multiple notebooks can execute in parallel

### Authentication Flow

1. Frontend obtains JWT from Clerk (`useAuth().getToken()`)
2. HTTP: Token injected via request interceptor (`Authorization: Bearer`)
3. WebSocket: Token sent in `authenticate` message after connection
4. Backend verifies JWT signature using Clerk's JWKS endpoint
5. User ID extracted from `sub` claim, used for authorization

## Limitations

- **No mutation tracking** - `df.append()`, `list.pop()` not detected
- **Single task only** - ECS runs 1 task for in-memory state consistency
- **Basic SQL escaping** - String substitution (not parameterized queries)
- **No cell reordering** - Cells maintain insertion order
- **No output history** - Only current execution state stored

## License

MIT
