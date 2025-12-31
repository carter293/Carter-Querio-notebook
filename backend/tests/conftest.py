"""Pytest configuration and shared fixtures for backend tests."""
import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Notebook, Cell, CellType, CellStatus, Graph, KernelState
from tests.test_utils import create_test_notebook, create_test_cell, load_test_notebook


@pytest.fixture
def test_notebook():
    """Create a basic test notebook with one cell."""
    return create_test_notebook(
        notebook_id="test-notebook",
        user_id="test-user",
        name="Test Notebook",
        cells=[
            create_test_cell(
                cell_id="cell1",
                cell_type=CellType.PYTHON,
                code="x = 1",
                status=CellStatus.SUCCESS,
                reads=set(),
                writes={"x"}
            )
        ]
    )


@pytest.fixture
def empty_notebook():
    """Create an empty test notebook."""
    return create_test_notebook(
        notebook_id="empty-notebook",
        user_id="test-user",
        name="Empty Notebook",
        cells=[]
    )


@pytest.fixture
def test_globals():
    """Create a test globals dictionary."""
    return {"__builtins__": __builtins__}


@pytest.fixture
def test_kernel():
    """Create a test kernel state."""
    return KernelState(globals_dict={"__builtins__": __builtins__})


# Test notebook fixtures that load from files in notebooks/test/
@pytest.fixture
def concurrency_test_notebook():
    """Load the test-concurrency notebook from test folder."""
    try:
        return load_test_notebook("test-concurrency")
    except FileNotFoundError:
        # Fallback to creating programmatically if file doesn't exist
        return create_test_notebook(
            notebook_id="test-concurrency",
            user_id="test-user",
            name="Concurrency Test"
        )


@pytest.fixture
def optimistic_test_notebook():
    """Load the test-optimistic notebook from test folder."""
    try:
        return load_test_notebook("test-optimistic")
    except FileNotFoundError:
        return create_test_notebook(
            notebook_id="test-optimistic",
            user_id="test-user",
            name="Optimistic Locking Test"
        )


@pytest.fixture
def create_delete_test_notebook():
    """Load the test-create-delete notebook from test folder."""
    try:
        return load_test_notebook("test-create-delete")
    except FileNotFoundError:
        return create_test_notebook(
            notebook_id="test-create-delete",
            user_id="test-user",
            name="Create/Delete Test"
        )


@pytest.fixture
def mixed_test_notebook():
    """Load the test-mixed notebook from test folder."""
    try:
        return load_test_notebook("test-mixed")
    except FileNotFoundError:
        return create_test_notebook(
            notebook_id="test-mixed",
            user_id="test-user",
            name="Mixed Operations Test"
        )

