# Notebook: Test Pandas
# DB: postgres://cllb18r8m0002mj08qn0e3j0b:bln4hxxo72tia00iyq04p4m9@querio.cluster-ro-cgavdplfhn3v.eu-central-1.rds.amazonaws.com:5432/cllb18r8m0002mj08qn0e3j0b?sslmode=require

# %% python [c1]
rows = 5


























# %% python [c2]
import pandas as pd

df = pd.DataFrame({
    'id': list(range(rows)),
    'value': [i * 10 for i in range(rows)]
})
df

