"""
Segments and tenure buckets shared by the pipeline scripts.

Each segment gets its own transition matrix. Bucket names are unique across
segments, so a bucket name alone identifies its segment.

Keep in sync with the CASE expressions in transition_query.sql and
scoring_query.sql.
"""

# segment -> tenure buckets in order (weeks since first settlement)
SEGMENT_BUCKETS = {
    "standard": [
        "standard_early",            # 2-4
        "standard_growing",          # 5-9
        "standard_mature",           # 10-19
        "standard_veteran",          # 20+
    ],
    "promo_2m_free": [
        "promo_free_period",         # 2-7  (free 2-month subscription)
        "promo_post_free_early",     # 8-12 (free period just ended)
        "promo_post_free",           # 13+
    ],
}

TENURE_ORDER = [b for buckets in SEGMENT_BUCKETS.values() for b in buckets]
BUCKET_TO_SEGMENT = {
    b: seg for seg, buckets in SEGMENT_BUCKETS.items() for b in buckets
}
