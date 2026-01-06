This document outlines the architectural vision and implementation plan for the **Querio Reactive Engine**.

This submission is designed to demonstrate Principal-level engineering capabilities: separation of concerns, defensive programming, rigid type safety, and architectural foresight. It avoids "bloat" (auth, persistence, deployment) to focus purely on the core technical challenge: **building a robust, reactive execution environment.**

---

# Architecture Design Document: The Reactive Kernel

## 1. Executive Summary
The proposed solution is a **Headless Reactive Kernel** engineered as an isolated OS process. It employs an **Actor Model** design where the Kernel processes messages sequentially, ensuring determinstic state management.

The architecture decouples the *runtime* (Kernel) from the *transport* (API/WebSockets) using the **Ports and Adapters** (Hexagonal) pattern. This ensures that while the initial implementation uses Python's `multiprocessing`, it could trivially be swapped for ZeroMQ or gRPC in a distributed production environment without refactoring the business logic.

## 2. High-Level System Architecture

The system consists of three distinct layers:

1.  **The Interface Layer (FastAPI):**
    *   Acts as the HTTP/WebSocket gateway.
    *   Stateless. Responds to health checks and brokers messages between the Client and the Orchestrator.
    *   **Responsibility:** Authentication (stubbed), Request Validation (Pydantic), Protocol Upgrading.

2.  **The Orchestration Layer:**
    *   Manages the lifecycle of the Kernel Process (Startup, Shutdown, Restart on Crash).
    *   Implements the `KernelInterface` protocol.
    *   **Responsibility:** Process supervision (Watchdog), Queue management, Correlation ID tracking.

3.  **The Kernel Layer (The Engine):**
    *   A separate OS process running a strict event loop.
    *   Contains the `DependencyGraph (DAG)`, `ASTParser`, and `Executor`.
    *   **Responsibility:** Code execution, Variable tracking, Standard IO capture, State mutation.

---

## 3. Core Component: The Reactive Engine

### 3.1. The Kernel Actor
The Kernel runs an infinite loop consuming structured `Command` objects from an `InputQueue`. It is strictly single-threaded to avoid race conditions on the user's `locals()` dictionary, but it uses `asyncio` to handle IO-bound output streaming effectively.

**The Loop:**
1.  **Receive:** Dequeue `ExecuteRequest`.
2.  **Parse:** `ASTParser` analyzes code to identify defined (`LHS`) and referenced (`RHS`) variables.
3.  **Graph Mutation:** Update the `NetworkX` DiGraph.
    *   *Constraint:* If a cycle is detected, roll back the graph change and emit `CircularDependencyError`.
4.  **Resolve:** Compute the execution subgraph (transitive closure of dependencies) via Topological Sort.
5.  **Execute:** Iterate through the subgraph:
    *   Redirect `sys.stdout` / `sys.stderr` to a `StreamCapture` buffer.
    *   Execute code via `exec()`.
    *   Capture outputs (MIME detection).
    *   Emit `CellResult` to `OutputQueue`.

### 3.2. AST Parsing and Scope Resolution
We will avoid regex entirely. We utilize Python's `ast` module to build a `SymbolTable`.
*   **Challenge:** Distinguishing between global variables and local function scopes.
*   **Solution:** A custom `ast.NodeVisitor` that only registers writes to the `Module` level scope, ignoring assignments inside `FunctionDef` or `ClassDef` nodes.

### 3.3. State Management
The execution context (`globals` dict) persists in memory within the Kernel process.
*   **Isolation:** The Kernel does not share memory with the API. It communicates strictly via serialized Pydantic models.

---

## 4. The "Novel" Feature: LLM-Native Reactivity

To solve the friction between LLMs (which output linear scripts) and Reactive Notebooks (which require modular cells), we introduce **"Semantic Cell Fission"**.

### The Concept
When an LLM provides a block of code, instead of dumping it into a single cell (which breaks reactivity), the Kernel acts as a "Just-In-Time Compiler" for the intent.

1.  **Ingestion:** The LLM sends a logical block of code (e.g., Load Data -> Clean Data -> Plot).
2.  **AST Fission:** The Kernel parses the AST and identifies independent dependency chains.
3.  **Atomic Splitting:** The Kernel automatically splits the code into distinct atomic cells based on variable dependency boundaries.
    *   *Example:* `df = load()` is separated from `plot(df)` because `df` is the edge connecting them.
4.  **Execution:** These validated atomic cells are inserted into the DAG.

**Why this is novel:** It allows the LLM to "think" in scripts but "act" in reactive components. It prevents the "Giant Cell" anti-pattern synonymous with AI-generated notebooks.

---

## 5. Engineering Standards ("God Level" Requirements)

To differentiate this submission from a standard mid-level implementation, we adhere to the following strict standards:

### 5.1. Protocols & Typing
We define the system behavior using Python `Protocols` (Interfaces) before implementation.
```python
class KernelProtocol(Protocol):
    async def start(self) -> None: ...
    async def execute(self, code: str, cell_id: str) -> ExecutionResult: ...
    async def interrupt(self) -> None: ...
```
*   **Strict Typing:** `mypy --strict` enabled. No `Any`.
*   **Pydantic V2:** All data moving between boundaries is strictly validated.

### 5.2. Structured Logging via `structlog`
No `print` statements. Logs must be machine-readable JSON for observability.
*   **Correlation IDs:** A unique `trace_id` is generated at the API ingress and passed into the Kernel process. This allows tracing a specific user action across process boundaries.
    ```json
    {"level": "info", "event": "cell_execution_start", "cell_id": "c1", "trace_id": "req-123"}
    ```

### 5.3. Defensive Error Handling
We implement a rich exception hierarchy:
*   `KernelError` (Base)
    *   `CompilationError` (Syntax)
    *   `RuntimeError` (Python exception)
    *   `GraphError` (Cycles)
    *   `SystemError` (Process crash)

The API converts these internal exceptions into standardized HTTP/WS Error Codes (e.g., `400 CONSTANT_CYCLE_DETECTED`).

### 5.4. The Watchdog Concept
A background thread in the API process monitors the Kernel process.
*   **Heartbeat:** If the Kernel hangs (`while True: pass`) and stops responding to heartbeats, the Watchdog performs a hard `SIGKILL`, restarts the process, and emits a `KernelRestarted` event to the frontend.

---

## 6. Implementation Plan (72 Hours)

### Day 1: The Core Engine (Pure Python)
*   **Goal:** A working DAG execution engine with 100% test coverage, no API.
*   **Tasks:**
    1.  Implement `ASTVisitor` for variable detection.
    2.  Implement `DependencyGraph` (NetworkX wrapper).
    3.  Implement `Kernel` actors logic.
    4.  **Critical:** Unit tests validating the "Reactive Behavior" (Cell A updates -> Cell B runs).

### Day 2: The Orchestrator & API
*   **Goal:** A FastAPI server creating and managing the Kernel process.
*   **Tasks:**
    1.  Setup `multiprocessing` queues and the "Main Loop".
    2.  Implement `StreamCapture` to redirect `stdout` to the queue.
    3.  Setup FastAPI WebSocket endpoint.
    4.  Implement `Pydantic` models for the communication protocol.

### Day 3: Frontend & Integration
*   **Goal:** Connect the provided UI code to the new robust engine.
*   **Tasks:**
    1.  Hook up the WebSocket.
    2.  Visual Polish: Add execution timers and status indicators.
    3.  **Documentation:** Write a `README.md` explaining the Architecture choices.

---

## 7. Submission Layout

```text
querio-engine/
├── backend/
│   ├── core/
│   │   ├── analysis/       # AST Parsing logic
│   │   ├── graph/          # DAG & Topology logic
│   │   └── protocol/       # Abstract Base Classes / Protocols
│   ├── kernel/
│   │   ├── runtime.py      # The Process Loop (Actor)
│   │   ├── executor.py     # Sandbox execution
│   │   └── io.py           # Stdout/Stderr capture
│   ├── orchestration/
│   │   ├── manager.py      # Process Lifecycle / Watchdog
│   │   └── queues.py       # Typed Queue wrappers
│   ├── server/             # FastAPI app
│   └── shared/             # Pydantic Schemas (Types)
├── frontend/               # (Existing React code)
├── tests/
│   ├── unit/               # Test Parse/Graph logic in isolation
│   └── integration/        # Test Process communication
├── pyproject.toml          # Poetry/Ruff/Mypy config
└── README.md
```


## Why use networkx ? 

This is a great question. In a "God Level" coding interview, every dependency needs a defense.

You should use **NetworkX**, but you must **encapsulate** it.

Here is the Senior Engineer reasoning for why you choose it, and how you defend it if questioned.

### 1. The "Solved Problem" Argument
Cycle detection and Topological sorting are "Solved Problems." Writing your own algorithm for this during a product build is often considered **Not Invented Here (NIH) Syndrome**.

*   **Junior Approach:** Writes a custom DFS (Depth First Search) recursion to find cycles. Likely misses an edge case where a node is visited twice in different paths, or blows the stack on a diamond dependency.
*   **Senior Approach:** Uses `nx.simple_cycles()` or `nx.is_directed_acyclic_graph()`. It is mathematically proven, battle-tested, and optimized.

### 2. The Specific Reactive Requirements
A reactive notebook isn't just a list; it is a **DAG (Directed Acyclic Graph)**. You need three specific mathematical operations that NetworkX provides out of the box:

*   **Topological Sort:** To know the execution order. If A->B and A->C and B->D, you must run A, then B, then D, then C (or C then B...).
    *   *NetworkX:* `list(nx.topological_sort(subgraph))`
*   **Transitive Closure (Descendants):** If I modify Cell 1, I need to know *every* downstream cell that is affected, not just the direct children.
    *   *NetworkX:* `nx.descendants(G, source_node)`
*   **Cycle Detection:** If User types `x = y` in Cell A and `y = x` in Cell B, the kernel must reject the execution instantly.
    *   *NetworkX:* `nx.find_cycle(G)` raises an exception immediately.

### 3. Performance Context
NetworkX is pure Python, which makes it "slow" for graphs with millions of nodes.
*   **Context:** A specific notebook will rarely have more than 100-200 cells.
*   **Verdict:** The overhead of NetworkX for <1000 nodes is measured in *microseconds*. It is negligible compared to the time it takes to execute one line of Python code or send a WebSocket message. Optimization here is premature.

### 4. The "God Level" Implementation Pattern
Do not let `networkx` objects leak throughout your codebase. That is sloppy. Use the **Repository Pattern** or a **Wrapper Class**.

**Do This (Encapsulation):**
Define your own internal representation of the dependency graph.

```python
# backend/core/graph/dependency_graph.py
import networkx as nx
from typing import List, Set

class DependencyGraph:
    def __init__(self):
        # We wrap NetworkX. If we want to switch to Rustworkx later,
        # we only change this file. The rest of the app doesn't know.
        self._graph = nx.DiGraph()

    def add_dependency(self, parent_id: str, child_id: str):
        """Register that child_id depends on parent_id."""
        self._graph.add_edge(parent_id, child_id)
        if not nx.is_directed_acyclic_graph(self._graph):
            self._graph.remove_edge(parent_id, child_id)
            raise CircularDependencyError(f"Cycle detected between {parent_id} and {child_id}")

    def get_execution_order(self, changed_cell_id: str) -> List[str]:
        """
        Returns a topologically sorted list of cells that need updates.
        """
        # 1. Get all downstream nodes (descendants)
        affected_nodes = nx.descendants(self._graph, changed_cell_id)
        affected_nodes.add(changed_cell_id)

        # 2. Create a subgraph of only affected items
        subgraph = self._graph.subgraph(affected_nodes)

        # 3. Sort them so dependencies always run first
        return list(nx.topological_sort(subgraph))
```

### Summary
Use NetworkX because it allows you to focus on the **Business Logic** (the orchestrator, the AST parsing, the actor model) rather than debugging heavy algorithmic implementation details. It shows you know how to pick the right tool for the job.