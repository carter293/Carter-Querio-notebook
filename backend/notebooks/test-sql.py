# Notebook: Test SQL

# %% python [c1]
user_id = 42

# %% sql [c2]
SELECT * FROM users WHERE id = {user_id}
