# Notebook: Demo Notebook
# DB: postgres://cllb18r8m0002mj08qn0e3j0b:bln4hxxo72tia00iyq04p4m9@querio.cluster-ro-cgavdplfhn3v.eu-central-1.rds.amazonaws.com:5432/cllb18r8m0002mj08qn0e3j0b?sslmode=require

# %% python [cell-1]
import pandas as pd
print("Hello from Python!")
users_table = 'users'


# %% sql [cell-2]
SELECT * FROM users limit 10 

