#!/usr/bin/env python3
"""
Test that demo notebook provisioning works with DynamoDB.
Usage: python scripts/test_demo_provision.py
"""
import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demo_notebook import create_demo_notebook
from storage import DYNAMODB_ENABLED, save_notebook, load_notebook, delete_notebook


async def test_demo_provision():
    """Test demo notebook creation and save."""
    print("🧪 Testing Demo Notebook Provisioning")
    print("-" * 60)
    print(f"Storage mode: {'DynamoDB' if DYNAMODB_ENABLED else 'File-based'}")
    print()
    
    # Create demo notebook
    test_user_id = "test-user-12345"
    demo = create_demo_notebook(test_user_id)
    demo.id = f"demo-{test_user_id}"
    
    print(f"✓ Created demo notebook")
    print(f"  - ID: {demo.id}")
    print(f"  - User: {demo.user_id}")
    print(f"  - Name: {demo.name}")
    print(f"  - Cells: {len(demo.cells)}")
    print()
    
    # Save to storage
    await save_notebook(demo)
    print(f"✓ Saved to {'DynamoDB' if DYNAMODB_ENABLED else 'file storage'}")
    print()
    
    # Load back
    loaded = await load_notebook(demo.id, test_user_id)
    print(f"✓ Loaded from {'DynamoDB' if DYNAMODB_ENABLED else 'file storage'}")
    print(f"  - Cells match: {len(loaded.cells) == len(demo.cells)}")
    print(f"  - Name match: {loaded.name == demo.name}")
    print(f"  - User ID match: {loaded.user_id == demo.user_id}")
    print()
    
    # Verify cell contents
    if len(loaded.cells) > 0:
        first_cell = loaded.cells[0]
        print(f"  - First cell type: {first_cell.type}")
        print(f"  - First cell code preview: {first_cell.code[:50]}...")
    print()
    
    # Cleanup
    await delete_notebook(demo.id, test_user_id)
    print(f"✓ Cleaned up test data")
    print()
    
    print(f"✅ Demo notebook provisioning works with {'DynamoDB' if DYNAMODB_ENABLED else 'file storage'}!")


if __name__ == "__main__":
    asyncio.run(test_demo_provision())

