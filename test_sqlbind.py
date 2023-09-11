import pytest

import sqlbind as s


def test_qmark():
    q = s.QMarkQueryParams(s.BaseDialect)
    assert q('field1 = {}', 10) == 'field1 = ?'
    assert q('field2 = {}', 20) == 'field2 = ?'
    assert q == [10, 20]


def test_numbered():
    q = s.NumericQueryParams(s.BaseDialect)
    assert q('field1 = {}', 10) == 'field1 = :1'
    assert q('field2 = {}', 20) == 'field2 = :2'
    assert q == [10, 20]


def test_format():
    q = s.Dialect.default_format()
    assert q('field1 = {}', 10) == 'field1 = %s'
    assert q('field2 = {}', 20) == 'field2 = %s'
    assert q == [10, 20]


def test_named():
    q = s.NamedQueryParams(s.BaseDialect)
    assert q('field1 = {}', 10) == 'field1 = :p0'
    assert q('field2 = {}', 20) == 'field2 = :p1'
    assert q == {'p0': 10, 'p1': 20}


def test_pyformat():
    q = s.Dialect.default_pyformat()
    assert q('field1 = {}', 10) == 'field1 = %(p0)s'
    assert q('field2 = {}', 20) == 'field2 = %(p1)s'
    assert q == {'p0': 10, 'p1': 20}


def test_conditions():
    q = s.Dialect.default()

    assert q.cond(True, 'field = {}', 10) == 'field = ?'
    assert q.cond(False, 'field = {}', 10) == ''

    assert q.not_none('field = {}', 20) == 'field = ?'
    assert q.not_none('field = {}', None) == ''

    assert q.is_true('field = {}', 30) == 'field = ?'
    assert q.is_true('field = {}', 0) == ''

    assert q.IN('field', None) == ''
    assert q.IN('field', []) == 'FALSE'
    assert q.IN('field', [10]) == 'field IN ?'

    assert q.eq('t.bar', None, boo='foo') == '(boo = ? AND t.bar is NULL)'
    assert q.neq('t.bar', None, boo='foo') == '(boo != ? AND t.bar is not NULL)'

    assert q == [10, 20, 30, [10], 'foo', 'foo']


def test_sqlite_in():
    q = s.Dialect.sqlite()

    assert q.IN('field', [10, '20']) == 'field IN (?,?)'
    assert q.IN('field', list(range(10)) + ['boo', 1.5]) == "field IN (0,1,2,3,4,5,6,7,8,9,'boo',1.5)"
    assert q == [10, '20']

    with pytest.raises(ValueError) as ei:
        q.IN('field', list(range(10)) + [object()])
    assert ei.match('Invalid type')


def test_logical_ops():
    q = s.Dialect.default()

    assert q('field = {}', 10) & q.not_none('gargbage', None) == 'field = ?'
    assert q('field = {}', 10) & '' == 'field = ?'
    assert q('field = {}', 10) & 'boo' == '(field = ? AND boo)'
    assert q.not_none('garbage', None) & '' == ''

    assert q('field = {}', 10) | q.not_none('gargbage', None) == 'field = ?'
    assert q('field = {}', 10) | '' == 'field = ?'
    assert q('field = {}', 10) | 'boo' == '(field = ? OR boo)'
    assert q.not_none('garbage', None) | '' == ''

    rv = q('field1 < {}', 10) | q('field2 > {}', 20) & q('field3 = {}', 30)
    assert rv == '(field1 < ? OR (field2 > ? AND field3 = ?))'


def test_prefix_join():
    q = s.Dialect.default()

    assert s.WHERE(q('boo'), q('foo'), 'bar') == 'WHERE boo AND foo AND bar'
    assert s.WHERE() == ''
    assert s.WHERE('', '') == ''

    assert s.WITH('', '') == ''
    assert s.WITH('boo', 'foo') == 'WITH boo, foo'


def test_set():
    q = s.Dialect.default()
    assert f'UPDATE table {q.SET(boo=10, foo=20)}' == 'UPDATE table SET boo = ?, foo = ?'


def test_where():
    q = s.Dialect.default()
    assert f'SELECT * FROM table {q.WHERE(boo=10, foo=None)}' == 'SELECT * FROM table WHERE (boo = ? AND foo is NULL)'
    assert q == [10]


def test_fields():
    q = s.Dialect.default()
    assert f'SELECT {s.FIELDS("boo", q.cond(False, "foo"))}' == 'SELECT boo'
