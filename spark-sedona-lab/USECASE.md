# Spark/Sedona Use cases

## One-sentence architecture

Airflow schedules a parameterized job; Spark builds and optimizes a lazy distributed DataFrame plan; Sedona contributes geometry/raster types, spatial predicates, partitioning and join strategies; Parquet/GeoParquet or a lakehouse table stores durable results; a serving system exposes the smaller curated outputs.

## Vocabulary

- **Driver:** builds plans, coordinates jobs, and holds only bounded results.
- **Executor:** worker process that runs tasks and stores shuffled/cached partitions.
- **Partition:** smallest unit of parallel work and distributed storage.
- **Transformation:** lazy operation such as `select`, `filter`, or `join`.
- **Action:** triggers execution, such as `count`, `show`, `write`, or `collect`.
- **Shuffle:** network redistribution caused by joins, groupings, sorts, and repartitioning.
- **Narrow transformation:** output partition depends on one input partition.
- **Wide transformation:** output depends on many input partitions and usually creates a shuffle.
- **Catalyst:** Spark SQL logical/physical query optimizer.
- **AQE:** runtime plan adaptation based on observed statistics.
- **Data skew:** a few keys or spatial regions dominate work and create straggler tasks.

## Things to say

- Prefer Spark/Sedona built-in expressions over Python UDFs so the engine can optimize the plan.
- Filter columns and rows before a join; do not move data to the driver to perform business logic.
- Partition count must match data volume and available cores; more partitions are not automatically better.
- Storage partitioning such as `event_date=...` is different from Spark's in-memory execution partitions.
- Small-file accumulation is a lake maintenance problem, not merely a cosmetic issue.
- Spatial joins add bounding-box candidate generation, spatial partitioning/indexing, and exact predicate evaluation.
- CRS mistakes can silently produce wrong distances; longitude/latitude order and projected versus geographic units matter.
- Airflow owns dependencies, retries, schedules, SLAs, and observability. Spark/Sedona owns distributed computation.

## Red flags

- `collect()` or `toPandas()` on an unbounded dataset.
- Python row loops or scalar UDFs for logic available as Spark/Sedona expressions.
- Blindly calling `repartition(1000)`.
- Joining before filtering or projecting columns.
- Ignoring skew, shuffle spill, task stragglers, and file counts.
- Writing non-idempotent Airflow tasks without partition-aware overwrite/merge semantics.
- Treating HDFS as mandatory. Spark can read from object storage, lakehouse tables, JDBC sources, and local files.
