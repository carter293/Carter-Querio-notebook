import uuid
from models import Notebook, Cell, CellType, CellStatus

def create_demo_notebook() -> Notebook:
    cells = [
        Cell(
            id=str(uuid.uuid4()),
            type=CellType.PYTHON,
            code="x = 10  # Upstream variable",
            status=CellStatus.IDLE,
            reads=set(),
            writes={'x'}
        ),
        Cell(
            id=str(uuid.uuid4()),
            type=CellType.PYTHON,
            code="y = x + 5  # Depends on x",
            status=CellStatus.IDLE,
            reads={'x'},
            writes={'y'}
        ),
        Cell(
            id=str(uuid.uuid4()),
            type=CellType.PYTHON,
            code="""import matplotlib.pyplot as plt

# Matplotlib chart - rendered as PNG
plt.figure(figsize=(8, 5))
plt.plot([1, 2, 3], [x, y, 15], marker='o', linewidth=2)
plt.title(f"Matplotlib: Dependency Demo (x={x}, y={y})")
plt.xlabel("Step")
plt.ylabel("Value")
plt.grid(True, alpha=0.3)
plt.gcf()""",
            status=CellStatus.IDLE,
            reads={'x', 'y', 'plt'},
            writes={'plt'}
        ),
        Cell(
            id=str(uuid.uuid4()),
            type=CellType.PYTHON,
            code="""import pandas as pd

# Create DataFrame
df = pd.DataFrame({
    "category": ["A", "B", "C", "D"],
    "value": [x, y, x+y, x*2],
    "label": ["X", "Y", "Sum", "Double"]
})
df""",
            status=CellStatus.IDLE,
            reads={'x', 'y', 'pd'},
            writes={'df', 'pd'}
        ),
        Cell(
            id=str(uuid.uuid4()),
            type=CellType.PYTHON,
            code="""import plotly.express as px

# Plotly interactive chart - rendered as HTML
fig = px.bar(
    df,
    x="category",
    y="value",
    title=f"Plotly: Interactive Bar Chart (x={x})",
    labels={"value": "Amount", "category": "Category"},
    text="label",
    color="value",
    color_continuous_scale="viridis"
)
fig.update_traces(textposition='outside')
fig.update_layout(height=400)
fig""",
            status=CellStatus.IDLE,
            reads={'df', 'x', 'px'},
            writes={'fig', 'px'}
        ),
        Cell(
            id=str(uuid.uuid4()),
            type=CellType.PYTHON,
            code="""import altair as alt

# Altair chart - rendered as Vega-Lite JSON
chart = alt.Chart(df).mark_bar().encode(
    x=alt.X('category:N', title='Category'),
    y=alt.Y('value:Q', title='Value'),
    color=alt.Color('value:Q', scale=alt.Scale(scheme='viridis')),
    tooltip=['category', 'value', 'label']
).properties(
    title='Altair: Declarative Visualization',
    width=400,
    height=300
)
chart""",
            status=CellStatus.IDLE,
            reads={'df', 'alt'},
            writes={'chart', 'alt'}
        )
    ]

    notebook = Notebook(id="demo", cells=cells, revision=0)

    from graph import rebuild_graph
    rebuild_graph(notebook)

    return notebook
