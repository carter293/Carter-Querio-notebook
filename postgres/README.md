# PostgreSQL Docker Setup for Reactive Notebook

This directory contains everything needed to run a local PostgreSQL instance in Docker, seeded with the Iris dataset for use with the reactive notebook.

## 📋 Prerequisites

- **Docker** and **Docker Compose** installed and running
  - Verify installation: `docker --version` and `docker compose version`
  - [Install Docker Desktop](https://www.docker.com/products/docker-desktop/) if needed

## 🚀 Quick Start

### 1. Start the PostgreSQL Container

From the `postgres/` directory, run:

```bash
docker compose up -d
```

This will:
- Pull the PostgreSQL 16 Alpine image (if not already present)
- Create a container named `querio-postgres`
- Initialize the database with the Iris dataset
- Expose PostgreSQL on port `5432`

### 2. Verify the Setup

Check that the container is running:

```bash
docker compose ps
```

You should see the `querio-postgres` container with status "Up" and health status "healthy".

### 3. Connect to the Database

#### Option A: Using psql (Command Line)

```bash
docker compose exec postgres psql -U querio_user -d querio_db
```

Or from your local machine (if you have `psql` installed):

```bash
psql -h localhost -p 5432 -U querio_user -d querio_db
```

Password: `querio_password`

#### Option B: Using the Reactive Notebook

In your reactive notebook, use the following connection string:

```
postgresql://querio_user:querio_password@localhost:5432/querio_db
```

## 📊 Database Schema

The `iris` table contains the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key, unique identifier |
| `sepal_length_cm` | REAL | Sepal length in centimeters |
| `sepal_width_cm` | REAL | Sepal width in centimeters |
| `petal_length_cm` | REAL | Petal length in centimeters |
| `petal_width_cm` | REAL | Petal width in centimeters |
| `species` | VARCHAR(50) | Iris species (Iris-setosa, Iris-versicolor, Iris-virginica) |

**Indexes:**
- Primary key on `id`
- Index on `species` for faster filtering

## 🔍 Example SQL Queries

### View all records

```sql
SELECT * FROM iris LIMIT 10;
```

### Count records by species

```sql
SELECT species, COUNT(*) as count 
FROM iris 
GROUP BY species 
ORDER BY species;
```

### Average measurements by species

```sql
SELECT 
    species,
    AVG(sepal_length_cm) as avg_sepal_length,
    AVG(sepal_width_cm) as avg_sepal_width,
    AVG(petal_length_cm) as avg_petal_length,
    AVG(petal_width_cm) as avg_petal_width
FROM iris
GROUP BY species;
```

### Filter by species

```sql
SELECT * 
FROM iris 
WHERE species = 'Iris-setosa'
ORDER BY id;
```

## 🛠️ Management Commands

### Stop the container

```bash
docker compose down
```

### Stop and remove volumes (⚠️ deletes all data)

```bash
docker compose down -v
```

### View logs

```bash
docker compose logs postgres
```

### Follow logs in real-time

```bash
docker compose logs -f postgres
```

### Restart the container

```bash
docker compose restart postgres
```

### Access PostgreSQL shell directly

```bash
docker compose exec postgres psql -U querio_user -d querio_db
```

## 📁 Files in This Directory

- **`docker-compose.yml`** - Docker Compose configuration for PostgreSQL service
- **`init.sql`** - SQL script that creates the `iris` table and imports data from `Iris.csv`
- **`Iris.csv`** - The Iris dataset (150 records, 3 species, 50 samples each)
- **`README.md`** - This file

## 🔧 Configuration Details

### Connection Information

- **Host:** `localhost`
- **Port:** `5432`
- **Database:** `querio_db`
- **Username:** `querio_user`
- **Password:** `querio_password`

### Docker Configuration

- **Image:** `postgres:16-alpine` (lightweight, production-ready)
- **Container Name:** `querio-postgres`
- **Data Volume:** `postgres_data` (persists data between container restarts)
- **Health Check:** Configured to verify database readiness

## 📚 About the Iris Dataset

The Iris dataset was used in R.A. Fisher's classic 1936 paper, *The Use of Multiple Measurements in Taxonomic Problems*, and can also be found on the [UCI Machine Learning Repository](https://archive.ics.uci.edu/ml/datasets/iris).

**Dataset Characteristics:**
- **Total Records:** 150
- **Species:** 3 (Iris-setosa, Iris-versicolor, Iris-virginica)
- **Samples per Species:** 50
- **Features:** 4 measurements (sepal length/width, petal length/width)

One flower species (Iris-setosa) is linearly separable from the other two, but the other two are not linearly separable from each other.

## 🐛 Troubleshooting

### Container won't start

1. Check if port 5432 is already in use:
   ```bash
   lsof -i :5432
   ```
   If another PostgreSQL instance is running, stop it or change the port in `docker-compose.yml`.

2. Check Docker logs:
   ```bash
   docker compose logs postgres
   ```

### Can't connect to database

1. Verify the container is running:
   ```bash
   docker compose ps
   ```

2. Check the health status - wait until it shows "healthy"

3. Verify connection string format:
   ```
   postgresql://querio_user:querio_password@localhost:5432/querio_db
   ```

### Data not imported

1. Check initialization logs:
   ```bash
   docker compose logs postgres | grep -i "copy\|iris"
   ```

2. Recreate the container:
   ```bash
   docker compose down -v
   docker compose up -d
   ```

## 🔐 Security Note

⚠️ **For Development Only:** The credentials in this setup are for local development. Never use these credentials in production environments.
