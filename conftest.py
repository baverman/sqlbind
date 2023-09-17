import pytest
import sqlbind


@pytest.fixture(autouse=True)
def add_np(doctest_namespace):
    doctest_namespace['q'] = sqlbind.Dialect.default()
