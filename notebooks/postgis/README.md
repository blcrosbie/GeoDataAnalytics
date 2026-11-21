# PostGIS (local)

A throwaway local copy of the retired central warehouse: Postgres 17 with
PostGIS, h3 and pg_duckdb. It is built from `../../warehouse/docker` and
initialized with `../../warehouse/init-db`. Use it to experiment with a
serving database; the lake doesn't need it.

1. Copy `.env.example` to `.env` and fill in the values.
2. Run `docker compose up -d`.
3. Connect on `localhost:${POSTGRES_PORT}`.

The `LAKE_S3_*` defaults point at the old Wasabi bucket, which no longer
exists. Set them to an AWS read key and the AWS bucket if you want the
`lake.*` views.
