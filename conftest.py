import pytest
import sqlbind


class conn:
    @staticmethod
    def execute(query, parameters):
        pass


@pytest.fixture(autouse=True)
def set_doctest_ns(doctest_namespace):
    doctest_namespace['q'] = sqlbind.Dialect.default()
    doctest_namespace['sqlbind'] = sqlbind
    doctest_namespace['conn'] = conn
    doctest_namespace['AND_'] = sqlbind.AND_
    doctest_namespace['OR_'] = sqlbind.OR_
    doctest_namespace['not_none'] = sqlbind.not_none
    doctest_namespace['WHERE'] = sqlbind.WHERE
