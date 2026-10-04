"""Small Apache Spark + Sedona interview lab.

Run inside the official Apache Sedona container:
    spark-submit /opt/sedona-lab/jobs/01_spatial_join.py

The job demonstrates:
- lazy Spark DataFrame construction
- generated distributed point data
- geometry creation with Sedona SQL functions
- a point-in-polygon spatial join
- query-plan inspection
- GeoParquet write/read
- the danger of collect() versus bounded result retrieval
"""

from pathlib import Path

from pyspark.sql import functions as F
from sedona.spark import SedonaContext

APP_NAME = "spark-sedona-interview-lab"
OUTPUT_PATH = "/opt/sedona-lab/output/tampa_points_geoparquet"


def build_context():
    # The official Sedona image already contains the compatible Spark/Sedona JARs.
    spark_config = (
        SedonaContext.builder()
        .appName(APP_NAME)
        .master("local[*]")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )
    return SedonaContext.create(spark_config)


def main() -> None:
    sedona = build_context()
    sedona.sparkContext.setLogLevel("WARN")

    print("\n=== Runtime ===")
    print("Spark version:", sedona.version)
    print("Default parallelism:", sedona.sparkContext.defaultParallelism)

    # Build 250,000 synthetic GPS-like points without a Python UDF.
    # Spark only records a logical plan here; no rows are generated until an action runs.
    points = (
        sedona.range(0, 250_000, numPartitions=8)
        .withColumn("lon", F.lit(-82.85) + (F.col("id") % 1000) * F.lit(0.0007))
        .withColumn(
            "lat",
            F.lit(27.50) + (F.floor(F.col("id") / 1000) % 500) * F.lit(0.0008),
        )
        .withColumn("event_date", F.lit("2026-07-27"))
        .withColumn(
            "geometry",
            F.expr("ST_SetSRID(ST_Point(lon, lat), 4326)"),
        )
        .drop("lon", "lat")
    )

    zones = sedona.createDataFrame(
        [
            (
                "west",
                "POLYGON((-82.85 27.50,-82.62 27.50,-82.62 27.90,-82.85 27.90,-82.85 27.50))",
            ),
            (
                "central",
                "POLYGON((-82.62 27.50,-82.38 27.50,-82.38 27.90,-82.62 27.90,-82.62 27.50))",
            ),
            (
                "east",
                "POLYGON((-82.38 27.50,-82.15 27.50,-82.15 27.90,-82.38 27.90,-82.38 27.50))",
            ),
        ],
        ["zone_id", "wkt"],
    ).withColumn(
        "geometry",
        F.expr("ST_SetSRID(ST_GeomFromWKT(wkt), 4326)"),
    ).drop("wkt")

    points.createOrReplaceTempView("points")
    zones.createOrReplaceTempView("zones")

    spatial_counts = sedona.sql(
        """
        SELECT
            z.zone_id,
            COUNT(*) AS point_count
        FROM points p
        JOIN zones z
          ON ST_Contains(z.geometry, p.geometry)
        GROUP BY z.zone_id
        ORDER BY z.zone_id
        """
    )

    print("\n=== Physical plan: look for exchange/shuffle and Sedona spatial join operators ===")
    spatial_counts.explain(mode="formatted")

    print("\n=== Action triggers execution ===")
    spatial_counts.show(truncate=False)

    print("\n=== Partition counts ===")
    print("points partitions:", points.rdd.getNumPartitions())
    print("result partitions:", spatial_counts.rdd.getNumPartitions())

    print("\n=== Write GeoParquet ===")
    (
        points.repartition(8)
        .write.format("geoparquet")
        .mode("overwrite")
        .partitionBy("event_date")
        .save(OUTPUT_PATH)
    )

    reloaded = sedona.read.format("geoparquet").load(OUTPUT_PATH)
    print("Reloaded schema:")
    reloaded.printSchema()
    print("Reloaded count:", reloaded.count())

    # Safe because the query is explicitly bounded. Never collect an unbounded distributed table.
    sample = (
        reloaded.select("id", F.expr("ST_AsText(geometry)").alias("wkt"))
        .orderBy("id")
        .limit(5)
        .collect()
    )
    print("\n=== Bounded driver-side sample ===")
    for row in sample:
        print(row)

    print("\nOutput written to:", OUTPUT_PATH)
    sedona.stop()


if __name__ == "__main__":
    main()
