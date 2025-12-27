from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import router, NOTEBOOKS
from storage import list_notebooks, load_notebook, save_notebook
from demo_notebook import create_demo_notebook

app = FastAPI(title="Reactive Notebook")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    notebook_ids = list_notebooks()

    if notebook_ids:
        print(f"Loading {len(notebook_ids)} notebook(s)...")
        for notebook_id in notebook_ids:
            try:
                notebook = load_notebook(notebook_id)
                NOTEBOOKS[notebook_id] = notebook
                print(f"  ✓ Loaded: {notebook_id}")
            except Exception as e:
                print(f"  ✗ Failed: {notebook_id}: {e}")
    else:
        print("Creating demo notebook...")
        demo = create_demo_notebook()
        NOTEBOOKS[demo.id] = demo
        save_notebook(demo)
        print(f"  ✓ Created demo: {demo.id}")

app.include_router(router, prefix="/api")

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
