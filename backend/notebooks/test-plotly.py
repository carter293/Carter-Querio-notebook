# Notebook: Test Plotly

# %% python [c1]
import plotly.graph_objects as go

fig = go.Figure(data=[
    go.Bar(x=['A', 'B', 'C'], y=[3, 7, 2])
])
fig.update_layout(title='Bar Chart')
fig

