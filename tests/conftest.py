"""Guard destructive integration tests against accidental use of a non-test database."""

import os
import re

import pytest
from psycopg.conninfo import conninfo_to_dict


def validate_test_database_url(url: str) -> None:
    dbname = conninfo_to_dict(url).get("dbname", "")
    if not re.search(r"(?:^|[_-])test(?:$|[_-])", dbname.lower()):
        raise ValueError("TEST_DATABASE_URL must name a dedicated database with 'test' in its name")


@pytest.fixture
def test_database_url():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated PostgreSQL test database")
    validate_test_database_url(url)
    return url
