"""Measure TimescaleDB compression at a realistic volume (Tiger Data).

The 12 demo customers are too few rows for compression to matter, so this loads synthetic HOURLY vehicle
telemetry for many vehicles into a scratch hypertable, compresses it the same way the app's hypertables are
(segment by customer, order by time), prints the real before and after sizes, and drops the scratch table.
It never touches the app's tables.

Why hourly: compression works on each customer's rows within a chunk, so it needs plenty of rows per
customer per chunk. A reading a day leaves 7 rows per weekly chunk, and the per-batch overhead then costs
more than it saves (measured: 0.8x). Real connected-car telemetry is far denser than that.

    DATABASE_URL=postgresql://... python scripts/compression_demo.py [vehicles] [days]
"""

import os
import sys

from crossroads.db.repo import connect


def main(vehicles: int, days: int) -> None:
    conn = connect(os.environ["DATABASE_URL"], autocommit=True)
    conn.execute("DROP TABLE IF EXISTS demo_telemetry")
    conn.execute(
        "CREATE TABLE demo_telemetry (ts timestamptz NOT NULL, customer_id text NOT NULL, "
        "odometer int NOT NULL, fuel_pct int NOT NULL, speed_avg int NOT NULL)"
    )
    conn.execute("SELECT create_hypertable('demo_telemetry', 'ts', chunk_time_interval => INTERVAL '7 days')")
    conn.execute(
        "ALTER TABLE demo_telemetry SET (timescaledb.compress, timescaledb.compress_segmentby = 'customer_id', "
        "timescaledb.compress_orderby = 'ts')"
    )
    conn.execute(
        """INSERT INTO demo_telemetry
           SELECT now() - make_interval(hours => h), 'veh_' || v,
                  20000 + v * 7 + ((%s * 24) - h) * (1 + v %% 3), 10 + (h * 7 + v) %% 90, 25 + (h + v) %% 45
           FROM generate_series(1, %s) v, generate_series(0, %s * 24 - 1) h""",
        (days, vehicles, days),
    )
    rows = conn.execute("SELECT count(*) FROM demo_telemetry").fetchone()[0]
    for (chunk,) in conn.execute("SELECT show_chunks('demo_telemetry')").fetchall():
        conn.execute("SELECT compress_chunk(%s::regclass, if_not_compressed => true)", (chunk,))
    before, after = conn.execute(
        "SELECT before_compression_total_bytes, after_compression_total_bytes "
        "FROM hypertable_compression_stats('demo_telemetry')"
    ).fetchone()
    print(f"{rows:,} hourly rows ({vehicles:,} vehicles x {days} days)")
    print(f"before compression: {before / 1e6:.1f} MB   after: {after / 1e6:.1f} MB   "
          f"saved {100 * (1 - after / before):.0f}%  ({before / after:.1f}x)")
    conn.execute("DROP TABLE demo_telemetry")
    conn.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 500, int(sys.argv[2]) if len(sys.argv) > 2 else 90)
