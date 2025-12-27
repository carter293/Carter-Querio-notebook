-- Create the iris table
CREATE TABLE IF NOT EXISTS iris (
    id INTEGER PRIMARY KEY,
    sepal_length_cm REAL NOT NULL,
    sepal_width_cm REAL NOT NULL,
    petal_length_cm REAL NOT NULL,
    petal_width_cm REAL NOT NULL,
    species VARCHAR(50) NOT NULL
);

-- Import data from CSV file
-- COPY works here because the postgres user in Docker has superuser privileges
COPY iris(id, sepal_length_cm, sepal_width_cm, petal_length_cm, petal_width_cm, species)
FROM '/docker-entrypoint-initdb.d/Iris.csv'
WITH (FORMAT csv, HEADER true, DELIMITER ',');

-- Create an index on species for faster queries
CREATE INDEX idx_iris_species ON iris(species);

-- Verify the import
SELECT COUNT(*) as total_records FROM iris;
SELECT species, COUNT(*) as count FROM iris GROUP BY species ORDER BY species;

