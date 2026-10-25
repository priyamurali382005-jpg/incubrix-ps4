import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["JOBS_SYNC"] = "true"
os.environ["EVIDENCE_DIR"] = "./test_evidence"

import pytest
from app.db import init_db, get_conn


@pytest.fixture(autouse=True)
def clean_db():
    init_db()
    conn = get_conn()
    for table in (
        "posts",
        "destinations",
        "jobs",
        "idempotency",
        "certifications",
        "alerts",
    ):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.close()