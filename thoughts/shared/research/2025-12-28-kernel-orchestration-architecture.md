---
date: 2025-12-28T16:44:31Z
researcher: Matthew Carter
topic: "Kernel Orchestration Architecture for Reactive Notebooks"
tags: [research, architecture, jupyter, marimo, ecs, kernel-management, websockets, dynamodb]
status: complete
last_updated: 2025-12-28
last_updated_by: Matthew Carter
---

# Research: Kernel Orchestration Architecture for Reactive Notebooks

**Date**: 2025-12-28T16:44:31Z
**Researcher**: Matthew Carter

## Research Question

How should we architect a separated kernel and orchestration layer for the reactive notebook system, moving from the current monolithic in-process execution to a distributed architecture supporting multiple concurrent kernels? What patterns do Jupyter and Marimo use, and how can we implement this on AWS ECS/Fargate with proper session management and routing?

## Executive Summary

Based on extensive research into Jupyter's kernel protocol, Marimo's reactive execution model, AWS ECS orchestration patterns, and analysis of the current codebase, I recommend a **hybrid architecture** that:

1. **Separates kernel execution** from the FastAPI orchestration layer using containerized kernels on AWS Fargate
2. **Uses DynamoDB** for kernel session tracking with TTL-based lifecycle management
3. **Implements WebSocket routing** via ALB sticky sessions mapped to kernel task IPs
4. **Adopts Jupyter's protocol** (ZeroMQ → WebSocket bridge) for proven multi-kernel communication
5. **Maintains warm pool** of 2-3 pre-initialized kernels for instant response
6. **Spawns on-demand kernels** during burst traffic using Fargate Spot (70% cost savings)

**Time Constraint**: With 4 hours remaining, I recommend **Phase 1 only** - a simplified architecture using direct HTTP/WebSocket to Python kernels without full ZeroMQ implementation.

---

## Detailed Findings

### 1. Current Architecture Limitations

**Analysis**: [backend/main.py](backend/main.py), [backend/executor.py](backend/executor.py), [backend/routes.py](backend/routes.py)

#### Critical Constraints
- **Single Worker Required**: `--workers 1` due to in-memory `NOTEBOOKS` dict ([backend/main.py](backend/main.py))
- **No Process Isolation**: All notebooks share same Python interpreter ([backend/executor.py:80-161](backend/executor.py#L80-L161))
- **Blocking Execution**: Python cells block event loop despite `asyncio.sleep(0)` mitigation ([backend/executor.py:88-92](backend/executor.py#L88-L92))
- **No State Persistence**: Runtime outputs/errors lost on restart ([backend/storage.py](backend/storage.py))
- **File-Based Storage**: JSON files instead of database ([backend/storage.py:7-69](backend/storage.py#L7-L69))

#### Architecture Pattern
```
┌─────────────────────────────────────┐
│   FastAPI Server (Single Worker)   │
│  ┌──────────┐  ┌──────────┐        │
│  │Notebook 1│  │Notebook 2│        │
│  │ Kernel   │  │ Kernel   │        │
│  │(in-proc) │  │(in-proc) │        │
│  └──────────┘  └──────────┘        │
│         ↓              ↓            │
│    Shared globals_dict              │
└─────────────────────────────────────┘
```

**Implication**: Cannot scale horizontally, no fault isolation, resource contention between notebooks.

---

### 2. Jupyter Kernel Architecture (Proven Production Pattern)

**Sources**:
- [Jupyter Client Messaging Documentation](https://jupyter-client.readthedocs.io/en/stable/messaging.html)
- [JupyterHub Technical Overview](https://jupyterhub.readthedocs.io/en/latest/reference/technical-overview.html)
- [Jupyter Enterprise Gateway System Architecture](https://jupyter-enterprise-gateway.readthedocs.io/en/latest/contributors/system-architecture.html)

#### Core Components

**1. ZeroMQ Protocol (5 Channels)**
- **Shell**: Execute requests, introspection (ROUTER)
- **IOPub**: Broadcast execution results, stdout, status (PUB/SUB)
- **Control**: Interrupt, shutdown (ROUTER)
- **Stdin**: User input prompts (ROUTER)
- **Heartbeat**: Health monitoring

**2. WebSocket Bridge**
- Server multiplexes all 5 ZeroMQ channels into single WebSocket
- Endpoint: `/api/kernels/{kernel_id}/channels`
- Protocol: JSON-encoded messages with channel name and optional binary buffers

**3. JupyterHub Multi-User Pattern**
```
┌──────────────────────────────────────────┐
│           Configurable Proxy             │ (Node.js, routes traffic)
│       /hub → Hub | /user/X → User Server │
└──────────────────────────────────────────┘
              ↓                    ↓
    ┌─────────────────┐    ┌──────────────┐
    │   Hub (Tornado) │    │ User Server  │ (per user)
    │  - Auth         │    │  - Notebook  │
    │  - Spawner      │    │  - Kernels   │
    │  - DB (Postgres)│    └──────────────┘
    └─────────────────┘
```

**4. Kernel Provisioner Framework**
- **LocalProvisioner**: subprocess.Popen for local kernels
- **Custom Provisioners**: DockerSpawner, KubeSpawner, ECSSpawner
- Abstracts kernel lifecycle: pre-launch → spawn → poll → kill → cleanup

**5. State Management**
- **Session Manager**: Maps notebook paths to kernel IDs (SQLite/PostgreSQL)
- **Kernel Metadata**: Tracked in database
  - `kernel_id`, `session_id`, `notebook_path`, `connection_file`, `last_activity`
- **Connection Files**: JSON with ZeroMQ ports, IP, signature keys

#### Production Examples

**Netflix**:
- Runs notebooks on Titus (container platform)
- Developed Commuter for viewing/sharing notebooks at scale
- Direct production workflow execution on notebooks

**Amazon SageMaker Studio**:
- Uses KernelGateway architecture
- Kernels run in Docker containers on separate hosts
- Fully elastic compute resources

**Facebook CSS Platform**:
- JupyterHub on EKS with thousands of users
- 1000+ daily queries on petabyte-scale datasets

---

### 3. Marimo Reactive Execution Model

**Sources**:
- [Marimo Reactivity Guide](https://docs.marimo.io/guides/reactivity/)
- [Marimo Dataflow Blog](https://marimo.io/blog/dataflow)
- [Marimo GitHub - app.py](https://github.com/marimo-team/marimo/blob/main/marimo/_ast/app.py)

#### Key Insights

**1. Dependency Tracking**
- **Static AST Analysis**: Parses code without running (zero runtime overhead)
- **DAG Enforcement**: No cycles, no variable reassignment across cells
- **Graph Components**: `CellManager`, `DirectedGraph`, `Runner`

**2. Execution Model**
- **NOT separate kernels** - uses active virtual environment directly
- **One kernel per session** in a sub-thread (same Python process)
- **ASGI-based** (Starlette) with WebSocket communication
- **Sticky sessions required** for load balancing

**3. Multi-User Limitations**
- **No built-in isolation** - recommends Docker containers or JupyterHub
- **Horizontal scaling difficult**: "Session state is not serializable across machines"
- **Single-process design**: Sub-threads share memory

**4. Deployment Pattern**
```python
server = marimo.create_asgi_app()
    .with_app(path="/dashboard", root="./pages/dashboard.py")

app = FastAPI()
app.mount("/", server.build())
```

#### Applicability to Our System

**What We Should Adopt**:
- ✅ Static AST analysis for dependency tracking (already implemented in [backend/ast_parser.py](backend/ast_parser.py))
- ✅ Reactive DAG execution (already implemented in [backend/graph.py](backend/graph.py))
- ✅ WebSocket-based real-time updates (already implemented in [backend/websocket.py](backend/websocket.py))

**What We Should Avoid**:
- ❌ In-process kernel execution (current limitation we're trying to fix)
- ❌ Sub-thread model (insufficient isolation)
- ❌ Single-process architecture (prevents horizontal scaling)

**Verdict**: Marimo's reactive model is excellent for **single-user** or **low-concurrency** scenarios, but insufficient for **multi-tenant production** with isolation requirements.

---

### 4. AWS ECS Orchestration Patterns

**Sources**:
- [ECS Standalone Tasks Documentation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/standalone-tasks.html)
- [ECS Task Lifecycle](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-lifecycle-explanation.html)
- [Fargate Spot Deep Dive](https://aws.amazon.com/blogs/compute/deep-dive-into-fargate-spot-to-run-your-ecs-tasks-for-up-to-70-less/)

#### RunTask vs Service Decision

**Use RunTask (One-off Tasks)** ✅ Recommended for Kernels:
- Batch processing with clear start/finish
- Session-based workloads
- No automatic restart needed
- Spawned on-demand per user session

**Use ECS Service** ❌ Not Appropriate:
- Long-running applications (web servers)
- Need automatic restart/self-healing
- Load balancer integration for traffic distribution

#### Task Lifecycle States

```
PROVISIONING → PENDING → ACTIVATING → RUNNING →
DEACTIVATING → STOPPING → DEPROVISIONING → STOPPED → DELETED
```

**Key Timing Considerations**:
- **Startup Time**: 90+ seconds for cold Fargate tasks
- **Optimization**: Use warm pools, smaller images, zstd compression
- **Shutdown**: SIGTERM → 30s grace period → SIGKILL

#### Fargate vs EC2 Cost Analysis

| Launch Type | Cost Model | Best For | Notebook Kernel Fit |
|-------------|------------|----------|---------------------|
| **Fargate On-Demand** | Per-second billing<br>1 vCPU: $0.04/hr<br>1GB RAM: $0.004/hr | Short-lived, bursty workloads | ✅ Excellent - no idle costs |
| **Fargate Spot** | **70% discount**<br>2-min warning before termination | Fault-tolerant tasks | ✅ **BEST** - huge savings |
| **EC2** | Hourly billing regardless of usage | Long-running, high-utilization | ❌ Poor - pay for idle time |

**Cost Example** (1 vCPU, 2GB RAM, 30-min session):
- Fargate On-Demand: ~$0.03/session
- **Fargate Spot: ~$0.009/session** ⭐
- EC2 (m5.large @ 50% utilization): ~$0.048/hour

**Recommendation**: **Fargate Spot** for 70% cost savings on fault-tolerant notebook executions.

#### Auto-Scaling Patterns

**Capacity Provider Strategies**:

1. **Spot for steady state + On-Demand for burst** (aggressive savings):
   - Higher risk of interruption
   - Best for fault-tolerant workloads

2. **On-Demand for steady state + Spot for burst** (balanced):
   - Lower risk, smaller savings
   - Best for 24/7 availability needs

**For Kernels**: On-Demand warm pool (2-3 kernels) + Spot for burst traffic

#### Warm Pools vs Cold Starts

**Warm Pools** (EC2 only, not Fargate):
- **70 seconds faster** first task start
- **41 seconds faster** subsequent starts
- Pre-initialized instances in Stopped (free) or Running state
- Limitation: `ReuseOnScaleIn` not supported

**Trade-offs**:
- **Warm Pool**: Faster UX, resource overhead, requires capacity planning
- **Cold Start**: Zero idle cost, 90+ second latency, poor UX

**Recommendation**: Hybrid - small warm pool (2-3 kernels) + on-demand spawning

---

### 5. Session Management & TTL Strategies

**Sources**:
- [DynamoDB Session Management](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/data-modeling-schema-session-management.html)
- [DynamoDB TTL for Serverless](https://towardsdatascience.com/how-dynamodb-ttl-enhances-your-serverless-architecture-cdebf7f4a8eb/)
- [Session Timeout Best Practices](https://www.descope.com/learn/post/session-timeout-best-practices)

#### DynamoDB vs RDS Decision Matrix

| Factor | DynamoDB | RDS |
|--------|----------|-----|
| **Response Time** | Single-digit milliseconds | 10-50ms with connection pooling |
| **Scaling** | Automatic horizontal | Vertical, connection limits |
| **Connection Model** | Stateless HTTP | Connection pooling overhead |
| **TTL Support** | Native, zero cost | Manual cleanup via cron |
| **Serverless Fit** | Excellent | Requires VPC, connection management |
| **Cost** | Pay per request | Pay for instance 24/7 |

**Verdict**: **DynamoDB strongly recommended** for kernel session metadata.

#### Schema Design

```python
# DynamoDB Table: kernel_sessions
{
    "kernel_id": "kern_abc123",              # Partition Key
    "task_arn": "arn:aws:ecs:...:task/...",  # ECS task identifier
    "notebook_id": "notebook_xyz",           # Which notebook owns this
    "user_id": "user_456",                   # For multi-tenancy
    "status": "running",                     # running|idle|terminating|terminated
    "created_at": 1703779200,                # Unix epoch
    "last_active_at": 1703779500,            # Updated on each request
    "expires_at": 1703808000,                # TTL field (created_at + 8 hours)
    "websocket_connection_id": "conn_def789",# API Gateway connection
    "task_ip": "10.0.1.42",                  # Direct IP routing
    "task_port": 8888                        # Kernel port
}

# GSI: notebook_id-index (query kernels by notebook)
# GSI: user_id-index (query kernels by user)
```

#### TTL Strategy: Dual Timeout

**1. Absolute Timeout** (DynamoDB TTL):
- Hard limit: 8 hours from creation
- Set `expires_at = created_at + 28800`
- DynamoDB auto-deletes (eventual consistency, ~11 min avg delay)

**2. Idle Timeout** (Application-Level):
- Inactive threshold: 30 minutes
- EventBridge cron every 5 minutes → Lambda
- Query DynamoDB for `current_time - last_active_at > 1800`
- Call ECS `StopTask` API for expired kernels

**Graceful Shutdown**:
```python
# In kernel container
signal.signal(signal.SIGTERM, handle_shutdown)

def handle_shutdown(signum, frame):
    print("[SHUTDOWN] SIGTERM received")
    # 1. Stop accepting new requests
    # 2. Finish in-flight computations
    # 3. Save checkpoints (if applicable)
    # 4. Close WebSocket connections
    # 5. Update DynamoDB status="terminated"
    sys.exit(0)
```

#### Health Monitoring

**Heartbeat Pattern**:
- Kernel sends heartbeat every 30 seconds
- Updates `last_heartbeat_at` in DynamoDB
- Background monitor checks for zombies (no heartbeat for 120s)
- Cleanup procedure:
  1. Send SIGTERM (graceful)
  2. Wait 30s grace period
  3. Send SIGKILL (forced)
  4. Update DynamoDB status
  5. Clean up resources

---

### 6. WebSocket Routing & Connection Management

**Sources**:
- [WebSocket on AWS with ALB and ECS](https://techholding.co/blog/aws-websocket-alb-ecs)
- [ALB Sticky Sessions](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/sticky-sessions.html)
- [WebSocket Architecture Best Practices](https://ably.com/topic/websocket-architecture-best-practices)

#### Routing Approaches

**Option 1: ALB with Sticky Sessions** ⭐ Recommended

```
Client WebSocket
    ↓
ALB (sticky session cookie)
    ↓
FastAPI Orchestrator
    ↓ (kernel_id lookup in DynamoDB)
WebSocket Proxy → Kernel Task IP:8888
```

**Configuration**:
- Enable sticky sessions at target group level
- Duration-based (AWSALB cookie, 1 hour)
- Increase idle timeout: 60s → 3600s (1 hour)
- Target type: `ip` (for awsvpc network mode)

**Option 2: API Gateway + VPC Link**

```
Client WebSocket
    ↓
API Gateway WebSocket API
    ↓ (connectionId → kernel_id mapping)
VPC Link → Private NLB → Kernel Tasks
```

**Pros**: Managed service, built-in connection tracking
**Cons**: Additional cost, complexity, 10MB message limit

**Option 3: Service Discovery (AWS Cloud Map)**

```
Client → FastAPI → Cloud Map DNS lookup
    ↓
Direct IP routing to kernel task
```

**Pros**: Low latency, direct routing
**Cons**: No load balancing, manual connection management

**Recommendation**: **ALB with sticky sessions** for simplicity and reliability.

#### Connection State Management

**Mapping Pattern**:
```python
# DynamoDB: websocket_connections table
{
    "connection_id": "conn_abc",  # PK
    "kernel_id": "kern_123",
    "notebook_id": "notebook_xyz",
    "connected_at": 1703779200,
    "last_ping": 1703779500
}
```

**Reconnection Handling**:
```javascript
// Client-side exponential backoff
class RobustWebSocket {
    reconnect() {
        const delay = Math.min(
            500 * 2 ** this.attempt + Math.random() * 1000,
            30000  // Max 30s
        );
        setTimeout(() => this.connect(), delay);
    }
}
```

**Backend Reconnection Flow**:
1. On disconnect: Start 5-minute idle timer
2. If reconnect within 5 min: Cancel timer, reuse kernel
3. If timeout expires: Terminate kernel, clean up session

---

## Architecture Recommendations

### Phase 1: Simplified Kernel Separation (4-Hour Implementation)

Given the tight timeline, implement a **lightweight version** without full Jupyter protocol:

#### Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    ALB (Port 80/443)                    │
│         /api/* → FastAPI  |  /kernel/* → Kernels       │
└─────────────────────────────────────────────────────────┘
              ↓                              ↓
┌──────────────────────────┐    ┌────────────────────────┐
│  FastAPI Orchestrator    │    │  Kernel Containers     │
│  - Notebook CRUD         │    │  (Fargate Tasks)       │
│  - Dependency Graph      │    │                        │
│  - Kernel Lifecycle Mgmt │◄───┤  - Python Executor     │
│  - WebSocket Proxy       │    │  - WebSocket Server    │
│  - Session Tracking      │    │  - HTTP Health Check   │
└──────────────────────────┘    └────────────────────────┘
              ↓
      ┌──────────────┐
      │  DynamoDB    │
      │  - Sessions  │
      │  - Notebooks │
      └──────────────┘
```

#### Components

**1. Kernel Container** (New Service)

Create `backend/kernel_service/main.py`:

```python
from fastapi import FastAPI, WebSocket
from executor import execute_python_cell, execute_sql_cell
import asyncio

app = FastAPI()

# Shared kernel state per container
KERNEL_STATE = {"globals_dict": {"__builtins__": __builtins__}}

@app.websocket("/execute")
async def execute_cell(websocket: WebSocket):
    await websocket.accept()

    while True:
        message = await websocket.receive_json()

        if message["type"] == "execute":
            cell_type = message["cell_type"]
            code = message["code"]

            if cell_type == "python":
                result = execute_python_cell(code, KERNEL_STATE)
            elif cell_type == "sql":
                result = await execute_sql_cell(code, message["conn_string"])

            await websocket.send_json({
                "type": "result",
                "cell_id": message["cell_id"],
                "result": result.dict()
            })

@app.get("/health")
async def health():
    return {"status": "healthy"}
```

**Dockerfile** (`backend/kernel_service/Dockerfile`):

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8888
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8888"]
```

**2. FastAPI Orchestrator Changes**

Modify `backend/routes.py`:

```python
import boto3
import uuid

ecs_client = boto3.client('ecs')
dynamodb = boto3.resource('dynamodb')
sessions_table = dynamodb.Table('kernel_sessions')

@router.post("/notebooks/{notebook_id}/start_kernel")
async def start_kernel(notebook_id: str):
    """Spawn a new kernel container for notebook"""

    kernel_id = f"kern_{uuid.uuid4().hex[:8]}"

    # Launch ECS Fargate task
    response = ecs_client.run_task(
        cluster='notebook-cluster',
        taskDefinition='kernel-service:latest',
        launchType='FARGATE',
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': ['subnet-xxx'],
                'securityGroups': ['sg-xxx'],
                'assignPublicIp': 'ENABLED'
            }
        },
        tags=[
            {'key': 'kernel_id', 'value': kernel_id},
            {'key': 'notebook_id', 'value': notebook_id}
        ]
    )

    task_arn = response['tasks'][0]['taskArn']

    # Wait for task to reach RUNNING state
    waiter = ecs_client.get_waiter('tasks_running')
    await asyncio.to_thread(
        waiter.wait,
        cluster='notebook-cluster',
        tasks=[task_arn]
    )

    # Get task IP
    task = ecs_client.describe_tasks(
        cluster='notebook-cluster',
        tasks=[task_arn]
    )['tasks'][0]

    task_ip = task['attachments'][0]['details'][1]['value']

    # Store in DynamoDB
    sessions_table.put_item(Item={
        'kernel_id': kernel_id,
        'task_arn': task_arn,
        'notebook_id': notebook_id,
        'task_ip': task_ip,
        'task_port': 8888,
        'status': 'running',
        'created_at': int(time.time()),
        'last_active_at': int(time.time()),
        'expires_at': int(time.time()) + 28800  # 8 hours
    })

    return {
        "kernel_id": kernel_id,
        "kernel_url": f"ws://{task_ip}:8888/execute"
    }
```

**3. WebSocket Proxy** (Orchestrator)

```python
@router.websocket("/ws/notebooks/{notebook_id}")
async def notebook_websocket(websocket: WebSocket, notebook_id: str):
    await websocket.accept()

    # Get or create kernel
    session = sessions_table.query(
        IndexName='notebook_id-index',
        KeyConditionExpression='notebook_id = :nid AND status = :status',
        ExpressionAttributeValues={':nid': notebook_id, ':status': 'running'}
    ).get('Items', [None])[0]

    if not session:
        # Start new kernel
        kernel_info = await start_kernel(notebook_id)
        kernel_url = kernel_info["kernel_url"]
    else:
        kernel_url = f"ws://{session['task_ip']}:{session['task_port']}/execute"

    # Proxy messages between client and kernel
    async with websockets.connect(kernel_url) as kernel_ws:
        async def client_to_kernel():
            while True:
                msg = await websocket.receive_json()
                await kernel_ws.send(json.dumps(msg))

        async def kernel_to_client():
            while True:
                msg = await kernel_ws.recv()
                await websocket.send_text(msg)

        await asyncio.gather(client_to_kernel(), kernel_to_client())
```

**4. DynamoDB Tables**

```bash
# Create sessions table
aws dynamodb create-table \
    --table-name kernel_sessions \
    --attribute-definitions \
        AttributeName=kernel_id,AttributeType=S \
        AttributeName=notebook_id,AttributeType=S \
    --key-schema AttributeName=kernel_id,KeyType=HASH \
    --global-secondary-indexes \
        '[{"IndexName":"notebook_id-index","KeySchema":[{"AttributeName":"notebook_id","KeyType":"HASH"}],"Projection":{"ProjectionType":"ALL"}}]' \
    --billing-mode PAY_PER_REQUEST \
    --time-to-live-specification "Enabled=true,AttributeName=expires_at"
```

**5. ECS Infrastructure** (Terraform)

Create `terraform/kernel_service.tf`:

```hcl
resource "aws_ecs_cluster" "kernels" {
  name = "notebook-kernels"
}

resource "aws_ecs_task_definition" "kernel" {
  family                   = "kernel-service"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "1024"  # 1 vCPU
  memory                   = "2048"  # 2 GB

  container_definitions = jsonencode([{
    name      = "kernel"
    image     = "${aws_ecr_repository.kernel.repository_url}:latest"
    portMappings = [{
      containerPort = 8888
      protocol      = "tcp"
    }]
    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8888/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])

  execution_role_arn = aws_iam_role.ecs_execution.arn
  task_role_arn      = aws_iam_role.kernel_task.arn
}
```

#### Implementation Steps (Prioritized for 4 Hours)

**Hour 1: Infrastructure Setup**
- [ ] Create DynamoDB table `kernel_sessions`
- [ ] Create ECS cluster `notebook-kernels`
- [ ] Set up ECR repository for kernel image
- [ ] Configure VPC, subnets, security groups

**Hour 2: Kernel Service**
- [ ] Extract `executor.py` functions to `kernel_service/executor.py`
- [ ] Create `kernel_service/main.py` with WebSocket endpoint
- [ ] Build and push Docker image to ECR
- [ ] Test kernel container locally

**Hour 3: Orchestrator Integration**
- [ ] Add boto3 dependencies to orchestrator
- [ ] Implement `start_kernel()` endpoint
- [ ] Implement `stop_kernel()` endpoint
- [ ] Add DynamoDB session tracking
- [ ] Test kernel spawning via API

**Hour 4: WebSocket Proxy & Testing**
- [ ] Implement WebSocket proxy in orchestrator
- [ ] Update frontend to connect via new endpoint
- [ ] End-to-end testing
- [ ] Deploy to staging environment

#### Limitations of Phase 1

- No ZeroMQ protocol (simplified HTTP/WS)
- No warm pools (cold start every time)
- No Fargate Spot (use On-Demand first)
- Manual cleanup (no automated TTL handlers yet)
- Single kernel per notebook (no kernel pooling)

---

### Phase 2: Production-Ready Architecture (Future)

For **post-submission enhancements**, implement the full architecture:

#### Architecture Diagram

```
┌───────────────────────────────────────────────────────────────┐
│                 Application Load Balancer                      │
│           /api → Orchestrator  |  /kernel → Kernels           │
│              (Sticky Sessions Enabled)                         │
└───────────────────────────────────────────────────────────────┘
                    ↓                              ↓
┌────────────────────────────────┐    ┌──────────────────────────┐
│   FastAPI Orchestrator         │    │   Kernel Pool            │
│   (ECS Service, Auto-scaling)  │    │   (Fargate Spot Tasks)   │
│                                │    │                          │
│   - Notebook API (CRUD)        │    │   ┌────────────────┐    │
│   - Dependency Graph Engine    │    │   │ Warm Kernel 1  │    │
│   - Kernel Lifecycle Manager   │◄───┼───│ Warm Kernel 2  │    │
│   - Session Router             │    │   │ Warm Kernel 3  │    │
│   - WebSocket Multiplexer      │    │   └────────────────┘    │
│                                │    │                          │
│   - Jupyter Protocol Bridge    │    │   ┌────────────────┐    │
│     (ZMQ → WebSocket)          │    │   │ Active Kernels │    │
│                                │    │   │ (On-demand)    │    │
└────────────────────────────────┘    │   │ - user_123     │    │
              ↓                        │   │ - user_456     │    │
┌──────────────────────────┐          │   └────────────────┘    │
│      DynamoDB Tables     │          └──────────────────────────┘
│  ┌────────────────────┐  │
│  │ kernel_sessions    │  │ ◄─── EventBridge Rule (5 min)
│  │ - TTL: expires_at  │  │           ↓
│  └────────────────────┘  │      Lambda: Idle Checker
│  ┌────────────────────┐  │           ↓
│  │ notebooks          │  │      ECS StopTask API
│  │ (replaces JSON)    │  │
│  └────────────────────┘  │
│  ┌────────────────────┐  │
│  │ websocket_conns    │  │
│  └────────────────────┘  │
└──────────────────────────┘
              ↓
    EventBridge + Lambda
    (TTL cleanup handlers)
```

#### Enhanced Components

**1. Jupyter Protocol Integration**

Implement ZeroMQ bridge for compatibility:

```python
# kernel_service/zmq_server.py
import zmq
import asyncio
from jupyter_client.session import Session

class JupyterKernelServer:
    def __init__(self):
        self.context = zmq.Context()
        self.session = Session()

        # 5 ZeroMQ sockets
        self.shell_socket = self.context.socket(zmq.ROUTER)
        self.iopub_socket = self.context.socket(zmq.PUB)
        self.stdin_socket = self.context.socket(zmq.ROUTER)
        self.control_socket = self.context.socket(zmq.ROUTER)
        self.hb_socket = self.context.socket(zmq.REP)

        # Bind to ports
        self.shell_socket.bind("tcp://*:5001")
        self.iopub_socket.bind("tcp://*:5002")
        # ...

    async def handle_shell_message(self):
        while True:
            msg = await self.shell_socket.recv_multipart()
            # Parse Jupyter message format
            # Execute code
            # Send results to iopub
```

**2. Warm Pool Manager**

```python
# orchestrator/kernel_pool.py
class KernelPoolManager:
    def __init__(self, min_size=2, max_size=10):
        self.min_size = min_size
        self.max_size = max_size
        self.available_kernels = asyncio.Queue()

    async def maintain_pool(self):
        """Background task to keep warm pool at min_size"""
        while True:
            current_size = self.available_kernels.qsize()
            if current_size < self.min_size:
                # Spawn (min_size - current_size) kernels
                for _ in range(self.min_size - current_size):
                    kernel = await self.spawn_kernel()
                    await self.available_kernels.put(kernel)
            await asyncio.sleep(30)

    async def get_kernel(self, notebook_id: str):
        """Get kernel from pool or spawn new one"""
        if not self.available_kernels.empty():
            kernel = await self.available_kernels.get()
            # Assign to notebook
            return kernel
        else:
            # Spawn on-demand
            return await self.spawn_kernel()

    async def return_kernel(self, kernel_id: str):
        """Return kernel to pool after idle timeout"""
        # Reset kernel state
        # Put back in queue if pool not full
        pass
```

**3. Fargate Spot Integration**

```hcl
# terraform/kernel_service.tf
resource "aws_ecs_capacity_provider" "fargate_spot" {
  name = "FARGATE_SPOT"
}

resource "aws_ecs_cluster_capacity_providers" "kernels" {
  cluster_name = aws_ecs_cluster.kernels.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 2  # Keep 2 On-Demand for warm pool
  }

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 3  # 75% of burst traffic on Spot
  }
}
```

**4. Idle Timeout Lambda**

```python
# lambda/idle_kernel_cleaner.py
import boto3
import time

ecs = boto3.client('ecs')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('kernel_sessions')

def lambda_handler(event, context):
    """Run every 5 minutes via EventBridge"""

    current_time = int(time.time())
    idle_threshold = 1800  # 30 minutes

    # Query running kernels
    response = table.scan(
        FilterExpression='#status = :running',
        ExpressionAttributeNames={'#status': 'status'},
        ExpressionAttributeValues={':running': 'running'}
    )

    for session in response['Items']:
        last_active = session['last_active_at']

        if current_time - last_active > idle_threshold:
            # Stop task
            ecs.stop_task(
                cluster='notebook-kernels',
                task=session['task_arn'],
                reason='Idle timeout exceeded'
            )

            # Update status
            table.update_item(
                Key={'kernel_id': session['kernel_id']},
                UpdateExpression='SET #status = :terminated',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':terminated': 'terminated'}
            )

    return {'statusCode': 200}
```

**5. Migration to DynamoDB for Notebooks**

Replace file-based storage with DynamoDB:

```python
# DynamoDB Table: notebooks
{
    "notebook_id": "notebook_abc",  # PK
    "name": "My Analysis",
    "db_conn_string": "postgresql://...",
    "revision": 5,
    "cells": [  # Store as JSON
        {
            "cell_id": "cell_123",
            "type": "python",
            "code": "x = 10",
            "reads": [],
            "writes": ["x"]
        }
    ],
    "created_at": 1703779200,
    "updated_at": 1703779500,
    "user_id": "user_456"
}
```

**Benefits**:
- Atomic updates
- Optimistic locking via revision numbers
- Multi-user access without file locking
- Automatic backups
- Point-in-time recovery

---

## Considerations & Trade-offs

### Option Comparison

| Approach | Pros | Cons | Recommendation |
|----------|------|------|----------------|
| **Keep In-Process** | Simple, fast, no infra changes | No isolation, can't scale | ❌ Not viable long-term |
| **Separate Process (same VM)** | Moderate isolation, faster than containers | Single point of failure, limited scaling | ⚠️ OK for MVP, not production |
| **Docker on EC2** | Good isolation, cost-effective at scale | Complex orchestration, slower startup | ✅ Good for high-utilization |
| **Fargate Tasks** | Full isolation, elastic, no infrastructure | Cold start latency, higher cost per hour | ✅ **Best for bursty workloads** |
| **Fargate Spot** | 70% cost savings, full isolation | 2-min interruption warning | ✅ **Best value for fault-tolerant** |
| **Lambda** | Zero infrastructure, auto-scale | 15-min limit, cold starts, limited control | ❌ Not suitable for notebooks |

### Decision Matrix

**For 4-Hour Timeline**: Phase 1 (Simplified Fargate On-Demand)
**For Production**: Phase 2 (Full Jupyter protocol + Fargate Spot + Warm pools)

### Risk Assessment

| Risk | Mitigation |
|------|------------|
| **Cold start latency** | Implement warm pool of 2-3 kernels |
| **Fargate Spot interruption** | Use On-Demand for warm pool, Spot for burst |
| **WebSocket disconnections** | Exponential backoff reconnection, message buffering |
| **Zombie kernels** | Heartbeat monitoring, automated cleanup Lambda |
| **Cost overruns** | Set DynamoDB TTL, idle timeouts, CloudWatch alarms |
| **DynamoDB throttling** | Use on-demand billing mode, design for eventual consistency |
| **Security (multi-tenancy)** | Container isolation, IAM roles, network policies |

---

## Implementation Roadmap

### Immediate (Next 4 Hours) - Phase 1

1. **Infrastructure** (1 hour)
   - Create DynamoDB `kernel_sessions` table
   - Set up ECS cluster and task definition
   - Configure VPC networking

2. **Kernel Service** (1 hour)
   - Extract executor to standalone service
   - Containerize with health checks
   - Deploy to ECR

3. **Orchestrator** (1 hour)
   - Add kernel lifecycle endpoints
   - Implement session tracking
   - Test ECS task spawning

4. **Integration** (1 hour)
   - WebSocket proxy
   - Frontend updates
   - End-to-end testing

### Short-Term (Next Sprint)

- Implement warm pool manager
- Add Fargate Spot capacity provider
- Deploy idle timeout Lambda
- Set up CloudWatch dashboards

### Medium-Term (Next Month)

- Full Jupyter protocol bridge
- Migrate notebooks to DynamoDB
- Multi-user authentication
- Production monitoring & alerting

### Long-Term (Future)

- GPU kernel support (EC2 launch type)
- Kernel checkpoint/restore
- Multi-region deployment
- Advanced analytics on usage patterns

---

## Code References

### Current Codebase
- Executor logic: [backend/executor.py:80-235](backend/executor.py#L80-L235)
- WebSocket broadcaster: [backend/websocket.py:11-108](backend/websocket.py#L11-L108)
- Dependency graph: [backend/graph.py:11-106](backend/graph.py#L11-L106)
- Scheduler: [backend/scheduler.py:44-102](backend/scheduler.py#L44-L102)
- Models: [backend/models.py](backend/models.py)
- Storage: [backend/storage.py:7-69](backend/storage.py#L7-L69)

### External References
- [Jupyter Client Documentation](https://jupyter-client.readthedocs.io/)
- [JupyterHub ECS Spawner](https://github.com/crowdsecurity/jupyter-ecs-spawner)
- [AWS ECS Task Lifecycle](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-lifecycle-explanation.html)
- [DynamoDB TTL Documentation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html)

---

## Open Questions

1. **Storage Choice**: Should we migrate from JSON files to DynamoDB now or later?
   - **Recommendation**: Later - Phase 1 can keep JSON, migrate in Phase 2

2. **Kernel Pooling**: Warm pool size and scaling parameters?
   - **Recommendation**: Start with 2-3, monitor CloudWatch metrics, adjust based on usage patterns

3. **Cost Budget**: What's the acceptable cost per user session?
   - **Context**: Fargate Spot = $0.009/session (30 min, 1 vCPU, 2GB)

4. **Multi-Tenancy**: User authentication and authorization?
   - **Recommendation**: Defer to post-submission (use single-user for demo)

5. **Data Persistence**: Should kernel state be saved between sessions?
   - **Recommendation**: No - treat kernels as ephemeral for simplicity

---

## Final Recommendation

Given the **4-hour constraint**, I recommend:

### ✅ **Implement Phase 1**: Simplified Kernel Separation

**Core Features**:
- Separate kernel containers on Fargate On-Demand
- DynamoDB session tracking
- Basic HTTP/WebSocket communication (no ZeroMQ)
- Manual kernel lifecycle management
- Single kernel per notebook

**Why This Approach**:
1. **Achievable in 4 hours** with focused effort
2. **Demonstrates architectural separation** (key requirement)
3. **Proves containerization works** for notebooks
4. **Foundation for Phase 2** enhancements
5. **Minimal frontend changes** needed

**Post-Submission Enhancements** (Phase 2):
- Full Jupyter protocol compatibility
- Fargate Spot for cost savings
- Warm pool for instant response
- Automated TTL cleanup
- Production monitoring

**Risk Mitigation**:
- Start with single notebook to validate flow
- Keep existing in-process fallback during transition
- Test kernel spawning locally with Docker Compose first
- Document all assumptions and limitations clearly

---

## Related Research

- See companion document on Jupyter architecture patterns
- See companion document on Marimo reactive execution
- See companion document on DynamoDB session management best practices
- See companion document on WebSocket scaling patterns

---

**Last Updated**: 2025-12-28
**Status**: Complete - Ready for implementation decision
