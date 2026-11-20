"""
Lake target: the AWS S3 bucket that receives curated/ files.

Only curated data is uploaded: files a script has already cleaned and
transformed (Parquet / GeoParquet). Raw source files (TIGER zips, LODES CSVs,
FCC responses, the ACS Summary File) are never uploaded. They are free to
download again from the publisher, so scripts fetch them into local staging,
build from there and throw them away.

Each file is written once to local staging, then uploaded with its sha256 in
the object metadata.

  LAKE_TARGETS=aws             target name; default "aws". (A comma list still
                               works, primary first, but there is one bucket.)

Per target <NAME> (upper-cased in the variable names):

  LAKE_<NAME>_BUCKET           required
  LAKE_<NAME>_REGION           e.g. us-east-2
  LAKE_<NAME>_ENDPOINT         host only, no scheme; blank for AWS
  LAKE_<NAME>_PROFILE          ~/.aws profile to take credentials from, or
  LAKE_<NAME>_KEY_ID           static key pair (wins over PROFILE when set)
  LAKE_<NAME>_SECRET

The Wasabi mirror and its raw origin/ archive were dropped on 2026-11-19; AWS
holds the only copy.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from dataclasses import dataclass, field

log = logging.getLogger("lake")

SHA_META = "sha256"  # x-amz-meta-sha256 on every object we write


@dataclass
class Target:
    name: str
    bucket: str
    region: str
    endpoint: str = ""          # host only; "" = AWS
    profile: str = ""
    key_id: str = ""
    secret: str = ""
    _client: object = field(default=None, repr=False)

    @property
    def is_aws(self) -> bool:
        return not self.endpoint

    def url(self, key: str) -> str:
        return f"s3://{self.bucket}/{key.lstrip('/')}"

    def session(self):
        import boto3
        if self.key_id and self.secret:
            return boto3.Session(aws_access_key_id=self.key_id,
                                 aws_secret_access_key=self.secret,
                                 region_name=self.region or None)
        return boto3.Session(profile_name=self.profile or None, region_name=self.region or None)

    def client(self):
        if self._client is None:
            from botocore.config import Config
            kw = {"config": Config(retries={"max_attempts": 10, "mode": "adaptive"},
                                   s3={"addressing_style": "path" if self.endpoint else "auto"})}
            if self.endpoint:
                kw["endpoint_url"] = f"https://{self.endpoint}"
            self._client = self.session().client("s3", **kw)
        return self._client

    def credentials(self) -> tuple[str, str, str | None]:
        c = self.session().get_credentials()
        if c is None:
            sys.exit(f"lake target {self.name}: no credentials (set LAKE_{self.name.upper()}_PROFILE "
                     f"or _KEY_ID/_SECRET)")
        f = c.get_frozen_credentials()
        return f.access_key, f.secret_key, f.token

    # ---- object helpers -------------------------------------------------------
    def head(self, key: str) -> dict | None:
        from botocore.exceptions import ClientError
        try:
            return self.client().head_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def list(self, prefix: str) -> dict[str, int]:
        """key -> size for every object under prefix."""
        out: dict[str, int] = {}
        pages = self.client().get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix)
        for page in pages:
            for o in page.get("Contents", []):
                out[o["Key"]] = o["Size"]
        return out

    def upload(self, local: str, key: str, sha: str | None = None) -> None:
        from boto3.s3.transfer import TransferConfig
        sha = sha or sha256_file(local)
        self.client().upload_file(
            local, self.bucket, key,
            ExtraArgs={"Metadata": {SHA_META: sha}, "ContentType": content_type(key)},
            Config=TransferConfig(multipart_threshold=64 << 20, multipart_chunksize=64 << 20,
                                  max_concurrency=8),
        )
        h = self.head(key)
        size = os.path.getsize(local)
        if not h or h["ContentLength"] != size:
            raise RuntimeError(f"{self.name}: {key} size mismatch after upload "
                               f"(local {size}, remote {h and h['ContentLength']})")

    def download(self, key: str, local: str) -> None:
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
        self.client().download_file(self.bucket, key, local)


def content_type(key: str) -> str:
    return {
        ".parquet": "application/vnd.apache.parquet",
        ".pmtiles": "application/vnd.pmtiles",
        ".json": "application/json",
        ".csv": "text/csv",
        ".txt": "text/plain",
        ".zip": "application/zip",
        ".gz": "application/gzip",
    }.get(os.path.splitext(key)[1].lower(), "application/octet-stream")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _target_from_env(name: str) -> Target:
    p = f"LAKE_{name.upper()}_"
    bucket = os.getenv(p + "BUCKET")
    if not bucket:
        sys.exit(f"lake target {name}: {p}BUCKET is not set")
    return Target(name=name, bucket=bucket,
                  region=os.getenv(p + "REGION", ""),
                  endpoint=os.getenv(p + "ENDPOINT", "").removeprefix("https://").rstrip("/"),
                  profile=os.getenv(p + "PROFILE", ""),
                  key_id=os.getenv(p + "KEY_ID", ""),
                  secret=os.getenv(p + "SECRET", ""))


def load_targets(names: str | None = None) -> list[Target]:
    """Targets in LAKE_TARGETS order (or `names`; default "aws"), primary first."""
    names = names or os.getenv("LAKE_TARGETS") or "aws"
    return [_target_from_env(n.strip()) for n in names.split(",") if n.strip()]


def register_duckdb(con, targets: list[Target]) -> None:
    """One DuckDB S3 secret per target, scoped to its bucket."""
    for t in targets:
        key_id, secret, token = t.credentials()
        opts = ["TYPE s3", "KEY_ID ?", "SECRET ?", "REGION ?", "SCOPE ?"]
        args = [key_id, secret, t.region or "us-east-1", f"s3://{t.bucket}"]
        if token:
            opts.append("SESSION_TOKEN ?")
            args.append(token)
        if t.endpoint:
            opts += ["ENDPOINT ?", "URL_STYLE 'path'"]
            args.append(t.endpoint)
        con.execute(f"CREATE OR REPLACE SECRET lake_{t.name} ({', '.join(opts)})", args)


def publish(local: str, key: str, targets: list[Target]) -> str:
    """Upload one local file to every target under the same key. Returns sha256."""
    sha = sha256_file(local)
    for t in targets:
        t.upload(local, key, sha)
        log.info("  -> %s", t.url(key))
    return sha


def publish_tree(local_dir: str, prefix: str, targets: list[Target]) -> int:
    """Upload every file under local_dir to <prefix>/<relative path> on every target."""
    n = 0
    for root, _dirs, files in os.walk(local_dir):
        for fn in sorted(files):
            if fn.endswith(".tmp"):
                continue
            local = os.path.join(root, fn)
            rel = os.path.relpath(local, local_dir).replace(os.sep, "/")
            publish(local, f"{prefix.rstrip('/')}/{rel}", targets)
            n += 1
    return n
