import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["JOBS_SYNC"] = "true"

import pytest

from app.db import get_conn, init_db


@pytest.fixture(autouse=True)
def clean_db():
    init_db()

    conn = get_conn()

    try:
        for table in ("posts", "destinations", "jobs", "idempotency"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()
