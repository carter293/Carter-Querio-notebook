#!/usr/bin/env python3
"""Integration test for notebook API."""
import httpx
import asyncio
from pathlib import Path

BASE_URL = "http://localhost:8000"
NOTEBOOKS_DIR = Path(__file__).parent / "notebooks"

async def test_integration():
    async with httpx.AsyncClient() as client:
        # Create notebook
        print("Creating notebook...")
        resp = await client.post(f"{BASE_URL}/api/v1/notebooks/")
        assert resp.status_code == 200
        notebook_id = resp.json()["notebook_id"]
        print(f"✓ Created notebook: {notebook_id}")

        # Verify file exists
        file_path = NOTEBOOKS_DIR / f"{notebook_id}.py"
        assert file_path.exists()
        print(f"✓ File created: {file_path}")

        # Create cell
        print("Creating cell...")
        resp = await client.post(
            f"{BASE_URL}/api/v1/notebooks/{notebook_id}/cells/",
            json={"type": "python"}
        )
        assert resp.status_code == 200
        cell_id = resp.json()["cell_id"]
        print(f"✓ Created cell: {cell_id}")

        # Update cell
        print("Updating cell code...")
        resp = await client.put(
            f"{BASE_URL}/api/v1/notebooks/{notebook_id}/cells/{cell_id}",
            json={"code": "print('Hello, World!')"}
        )
        assert resp.status_code == 200
        print("✓ Cell updated")

        # Verify file content
        content = file_path.read_text()
        assert "print('Hello, World!')" in content
        assert f"# %% python [{cell_id}]" in content
        print("✓ File content correct")

        # Get notebook
        print("Fetching notebook...")
        resp = await client.get(f"{BASE_URL}/api/v1/notebooks/{notebook_id}")
        assert resp.status_code == 200
        notebook = resp.json()
        assert len(notebook["cells"]) == 1
        assert notebook["cells"][0]["code"] == "print('Hello, World!')"
        print("✓ Notebook fetched correctly")

        # Delete notebook
        print("Deleting notebook...")
        resp = await client.delete(f"{BASE_URL}/api/v1/notebooks/{notebook_id}")
        assert resp.status_code == 200
        assert not file_path.exists()
        print("✓ Notebook deleted")

        print("\n✅ All integration tests passed!")

if __name__ == "__main__":
    asyncio.run(test_integration())
