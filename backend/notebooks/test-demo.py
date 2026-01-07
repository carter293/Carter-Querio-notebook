# Notebook: Demo Notebook
# DB: postgresql://querio_user:querio_password@localhost:5432/querio_db

# %% python [cell-1]
import pandas as pd
print("Hello from Python!")
users_table = 'users'



# %% sql [cell-2]
SELECT * FROM users limit 10 

