# Notebook: Test Matplotlib

# %% python [c1]
n = 10

# %% python [c2]
import matplotlib.pyplot as plt
import numpy as np

x = np.arange(n)
y = np.random.rand(n)

fig, ax = plt.subplots()
ax.plot(x, y)
ax.set_title(f'Data points: {n}')
fig

