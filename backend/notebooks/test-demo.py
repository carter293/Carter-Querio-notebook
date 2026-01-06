# Notebook: Demo Notebook
# DB: postgresql://localhost/testdb

# %% python [cell-1]
import pandas as pd
print("Hello from Python!")

# %% sql [cell-2]
SELECT * FROM users LIMIT 10

# %% python [cell-3]
df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
df.head()
