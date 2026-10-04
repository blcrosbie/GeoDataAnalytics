# Spark + Apache Sedona Interview Lab

This lab is intentionally small. It teaches Spark/Sedona execution semantics on one machine; it does **not** pretend Docker Desktop is a production cluster.

## Start the official Sedona image

```bash
docker compose pull
docker compose up -d
docker compose logs -f sedona
```

Open Jupyter at <http://localhost:8888>. The container logs normally show the access token or URL.

## Run the spatial job

```bash
docker compose exec sedona \
  spark-submit /opt/sedona-lab/jobs/01_spatial_join.py
```

While the job is active, inspect the Spark UI at <http://localhost:4040>.

The job creates 250,000 synthetic point records, performs a point-in-polygon join, prints the physical plan, writes partitioned GeoParquet, reads it back, and retrieves only a bounded five-row sample to the driver.

## Inspect the output

```bash
find output -maxdepth 3 -type f | sort | head -30
```

Expect multiple `part-...parquet` files. That is normal: distributed writers write partitions concurrently. A demand for one giant output file is commonly a downstream-interface smell.

## Shut down

```bash
docker compose down
```

## What to observe

1. DataFrame transformations do not execute immediately.
2. `show()`, `count()`, writes, and `collect()` are actions.
3. `explain("formatted")` exposes the optimized and physical plans.
4. A spatial join is still a distributed join and may require repartitioning/shuffling.
5. GeoParquet preserves geometry metadata and supports spatially useful metadata/pushdown.
6. Airflow should submit and monitor work; it should not carry a giant dataset through XCom.

## Airflow/Wherobots reference

`dags/wherobots_spatial_etl_example.py` is a reference DAG using `WherobotsSqlOperator`. It is intentionally separate from the local compose stack because Airflow is orchestration and Wherobots supplies managed compute.
