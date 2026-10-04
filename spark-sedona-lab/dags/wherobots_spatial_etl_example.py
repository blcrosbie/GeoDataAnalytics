"""Reference Airflow DAG for discussing Wherobots orchestration.

This is not part of the local Docker runtime. It requires:
    pip install airflow-providers-wherobots
and an Airflow connection named `wherobots_default` containing an API key.
"""

import datetime

from airflow import DAG
from airflow_providers_wherobots.operators.sql import WherobotsSqlOperator
from wherobots.db.region import Region
from wherobots.db.runtime import Runtime

with DAG(
    dag_id="daily_spatial_enrichment",
    start_date=datetime.datetime(2026, 7, 1),
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    tags=["wherobots", "sedona", "spatial-etl"],
) as dag:
    enrich_daily_partition = WherobotsSqlOperator(
        task_id="enrich_daily_partition",
        region=Region.AWS_US_WEST_2,
        runtime=Runtime.TINY,
        sql="""
        INSERT INTO org_catalog.analytics.daily_asset_zone_counts
        SELECT
            '{{ ds }}' AS event_date,
            zones.zone_id,
            COUNT(*) AS asset_count
        FROM org_catalog.raw.asset_positions AS assets
        JOIN org_catalog.reference.service_zones AS zones
          ON ST_Contains(zones.geometry, assets.geometry)
        WHERE assets.event_time >= TIMESTAMP '{{ ds }} 00:00:00'
          AND assets.event_time <  TIMESTAMP '{{ next_ds }} 00:00:00'
        GROUP BY zones.zone_id
        """,
        return_last=False,
    )
