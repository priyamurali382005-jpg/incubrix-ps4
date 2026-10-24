
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest

from app.db import get_conn, init_db


@pytest.fixture(autouse=True)
def clean_db():
    init_db()

    conn = get_conn()

    try:
        conn.execute("DELETE FROM posts")
        conn.execute("DELETE FROM destinations")
        conn.commit()
    finally:
        conn.close()
