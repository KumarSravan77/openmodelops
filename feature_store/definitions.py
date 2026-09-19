from datetime import timedelta

from feast import Entity, FeatureView, Field, FileSource
from feast.types import Float32, Int64

account = Entity(name="account_id", join_keys=["account_id"])
account_source = FileSource(
    path="data/account_features.parquet",
    timestamp_field="event_timestamp",
    created_timestamp_column="created_timestamp",
)
account_features = FeatureView(
    name="account_features",
    entities=[account],
    ttl=timedelta(days=1),
    schema=[
        Field(name="activity_count_24h", dtype=Int64),
        Field(name="risk_score", dtype=Float32),
    ],
    source=account_source,
    online=True,
)
