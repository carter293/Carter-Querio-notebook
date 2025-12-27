# querio take-home-2

Build a reactive notebook interface where code cells automatically re-execute when their dependencies change.

## The Problem

At Querio, we're building AI-powered analytics for regular users (non-data teams), bypassing traditional data team bottlenecks. An LLM generates Python code that creates interactive dashboards and analytics - but this code needs to run somewhere. That "somewhere" is a reactive notebook.

Traditional BI tools (PowerBI, Looker) require pre-built semantic layers and rigid schemas. Pure notebooks (Jupyter) require programming knowledge. We need something in between: a reactive execution environment that:

- Provides rich output capabilities (charts, tables, interactive controls)
- Is usable by an AI agent, as well as a human
- Updates automatically when inputs change (reactive behaviour)

Traditional notebooks (like Jupyter) have critical issues:

1. **Manual Execution**: Users must remember which cells to re-run after changes
2. **Inconsistent State**: Cells can be out of sync, showing stale outputs
3. **Execution Order**: Non-linear execution leads to hidden dependencies

**Traditional Jupyter Workflow:**

```python
Cell 1: x = 10
Cell 2: y = x + 5    # y = 15
Cell 3: z = y * 2    # z = 30

# User changes Cell 1
Cell 1: x = 20
# Problem: Cells 2 and 3 still show old values (y=15, z=30)
# User must manually re-run Cell 2 and Cell 3 to see y=25, z=50
```

This gets exponentially worse with AI-generated notebooks containing dozens of cells with intricate dependencies.

A **reactive notebook** automatically tracks dependencies between cells and re-executes them when upstream values change - like a spreadsheet.

**Reactive Behavior:**

```python
Cell 1: x = 10
Cell 2: y = x + 5    # y = 15 (depends on x)
Cell 3: z = y * 2    # z = 30 (depends on y)

# User edits Cell 1 to x = 20
# System automatically detects that Cell 2 depends on x
# Automatically re-runs Cell 2 → y becomes 25
# Detects Cell 3 depends on y
# Automatically re-runs Cell 3 → z becomes 50
# All done instantly, notebook is always in consistent state ✨

```

## Core Requirements

- **Notebook setup**
    - Add database connection string (only Postgres), which will be used by all SQL cells
- **Cell Management**
    - Add new cells (button or keyboard shortcut)
    - Edit cell code (text editor/textarea)
    - Delete cells
    - Each cell shows its code and output
    - Running a cell generates its output (or error)
    - Support SQL cells natively, not SQL wrapped in Python (in the frontend)
- **Visual Feedback**
    - Execution status indicators (idle/running/success/error)
    - Display cell outputs (text, numbers, DataFrames, errors)
- **Reactive Updates**
    - When user runs an upstream cell, trigger downstream execution
    - Show loading/running state for cells being executed
    - Update outputs live as cells complete
    - No manual "run" buttons needed (though optional for explicit control)

## Keep in Mind

- You must use Python and/or Typescript.
- The app must be free of significant flaws (including crashes, glitches, incorrect business logic, etc).

<aside>
‼️

Feel free to use any tools (this includes LLMs) and take your implementation in any direction that meets the requirements. 

</aside>

## Evaluation

Your submission will be evaluated on code quality, technology choices, problem fit, encapsulation hierarchy, maintainability, extensibility, and overall technical taste. 

## Submission

Push your code to a public repo and share the link with [nik@querio.ai](mailto:nik@querio.ai), [mo@querio.ai](mailto:mo@querio.ai) and [jb@querio.ai](mailto:jb@querio.ai). Spend as much time as you want, but **submit within 72 hours**. 

Regardless of outcome, we'll provide detailed feedback on your work.