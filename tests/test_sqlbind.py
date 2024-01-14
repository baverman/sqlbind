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

    assert q.not_empty('field = {}', 30) == 'field = ?'
    assert q.not_empty('field = {}', 0) == ''
    assert q == [10, 20, 30]


def test_outbound_conditions():
    q = s.Dialect.default()

    assert q('field = {}', s.cond(True)/10) == 'field = ?'
    assert q('field = {}', s.cond(False)/10) == ''

    assert q.eq('field', s.not_none/20) == 'field = ?'
    assert q.eq('field', s.not_none/None) == ''

    assert q('field = {}', s.truthy/30) == 'field = ?'
    assert q('field = {}', s.truthy/0) == ''
    assert q == [10, 20, 30]


def test_query_methods():
    q = s.Dialect.default()
    assert q.IN('field', s.truthy/0) == ''
    assert q.IN('field', None) == ''
    assert q.IN('field', []) == 'FALSE'
    assert q.field.IN([10]) == 'field IN ?'

    assert q.eq('t.bar', None, boo='foo') == '(boo = ? AND t.bar IS NULL)'
    assert q.neq('t.bar', None, boo='foo') == '(boo != ? AND t.bar IS NOT NULL)'
    assert q.neq('t.bar', s.not_none/None, boo=s.not_none/None) == ''

    assert q == [[10], 'foo', 'foo']

    q = s.Dialect.default()
    assert q.in_range(q.val, 10, 20) == '(val >= ? AND val < ?)'
    assert q.in_crange(q._.c.val, 10, 20) == '(c.val >= ? AND c.val <= ?)'
    assert q == [10, 20, 10, 20]


def test_bind():
    q = s.Dialect.sqlite()
    assert q/10 == '?'
    assert q == [10]


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

    assert ~q('TRUE') == 'NOT TRUE'
    assert ~s.EMPTY == ''


def test_prefix_join():
    q = s.Dialect.default()

    assert s.WHERE(q('boo'), q('foo'), 'bar') == 'WHERE boo AND foo AND bar'
    assert s.WHERE() == ''
    assert s.WHERE('', '') == ''

    assert s.WITH('', '') == ''
    assert s.WITH('boo', 'foo') == 'WITH boo, foo'


def test_prepend():
    q = s.Dialect.default()
    assert s.AND_('') == ''
    assert s.AND_(q.f == s.not_none/None) == ''
    assert s.AND_(q.f == s.not_none/10) == 'AND f = ?'
    assert q == [10]

    q = s.Dialect.default()
    assert s.OR_('') == ''
    assert s.OR_(q.f == s.not_none/None) == ''
    assert s.OR_(q.f == s.not_none/10) == 'OR f = ?'
    assert q == [10]


def test_set():
    q = s.Dialect.default()
    assert f'UPDATE table {q.SET(boo=10, foo=20)}' == 'UPDATE table SET boo = ?, foo = ?'


def test_where():
    q = s.Dialect.default()
    assert f'SELECT * FROM table {q.WHERE(boo=10, foo=None)}' == 'SELECT * FROM table WHERE (boo = ? AND foo IS NULL)'
    assert q == [10]


def test_fields():
    q = s.Dialect.default()
    assert f'SELECT {s.FIELDS("boo", q.cond(False, "foo"))}' == 'SELECT boo'


def test_limit():
    q = s.Dialect.default()
    assert q.LIMIT(s.not_none/None) == ''
    assert q.LIMIT(20) == 'LIMIT ?'
    assert q.OFFSET(s.not_none/None) == ''
    assert q.OFFSET(20) == 'OFFSET ?'


def test_qexpr():
    q = s.Dialect.default()

    assert (q.val < 1) == 'val < ?'
    assert (q.val <= 2) == 'val <= ?'
    assert (q.val > 3) == 'val > ?'
    assert (q.val >= 4) == 'val >= ?'
    assert (q.val == 5) == 'val = ?'
    assert (q.val != 6) == 'val != ?'
    assert q == [1, 2, 3, 4, 5, 6]

    assert (q.val == s.not_none/None) is s.EMPTY
    assert (q.val == s.truthy/0) is s.EMPTY
    assert q == [1, 2, 3, 4, 5, 6]

    q = s.Dialect.default()
    assert (q._('field + 10') < 1) == 'field + 10 < ?'
    assert q == [1]


def test_dialect_descriptor():
    class Q:
        p = s.Dialect(s.Dialect.default)

    q1 = Q.p
    q1/10

    q2 = Q.p
    q2/20

    assert q1 == [10]
    assert q2 == [20]


def test_like_escape():
    assert s.like_escape('boo') == 'boo'
    assert s.like_escape('boo%') == 'boo\\%'
    assert s.like_escape('boo_') == 'boo\\_'
    assert s.like_escape('boo\\') == 'boo\\\\'
    assert s.like_escape('%b\\oo_|', '|') == '|%b\\oo|_||'


def test_like():
    q = s.Dialect.default()
    q.tag.LIKE('{}%', 'my_tag') == 'tag LIKE ?'
    q.tag.ILIKE('{}%', 'my_tag') == 'tag ILIKE ?'
    assert q == ['my\\_tag%', 'my\\_tag%']
