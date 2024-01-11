import typing as t

version = '1.1'

Str = t.Union[str, 'QExpr']


class Expr(str):
    """Expr is a result of QueryParams rendering

    It provides basic &, | and ~ operations to compose
    expressions without lowering to string operations.

    Technically Expr instances are strings and could be used
    freely in string context.

    >>> (q.field > 10) & (q.field < 20) & ~q.enabled
    '((field > ? AND field < ?) AND NOT enabled)'

    >>> (q('name = {}', 'bob') | 'enabled = 1')
    '(name = ? OR enabled = 1)'
    """
    def __or__(self, other: str) -> 'Expr':
        return OR(self, other)

    def __and__(self, other: str) -> 'Expr':
        return AND(self, other)

    def __invert__(self) -> 'Expr':
        if self:
            return Expr('NOT ' + self)
        else:
            return EMPTY


def join_fragments(sep: str, fragments: t.Sequence[Str], wrap: t.Optional[str] = None) -> Expr:
    fragments = list(filter(None, fragments))
    if not fragments:
        return EMPTY
    elif len(fragments) == 1:
        return Expr(str(fragments[0]))

    e = sep.join(map(str, fragments))
    if wrap:
        e = wrap.format(e)
    return Expr(e)


def OR(*fragments: Str) -> Expr:
    """Joins parts with OR

    >>> OR('enabled = 1', q.date < '2020-01-01')
    '(enabled = 1 OR date < ?)'
    """
    return join_fragments(' OR ', fragments, '({})')


def AND(*fragments: Str) -> Expr:
    """Joins parts with AND

    >>> AND('enabled = 1', q.date < '2020-01-01')
    '(enabled = 1 AND date < ?)'
    """
    return join_fragments(' AND ', fragments, '({})')


def AND_(*fragments: Str) -> str:
    """Allows to make dynamic additions into existing static WHERE clause

    >>> date = None
    >>> f'SELECT * from users WHERE enabled = 1 {AND_(q.registration_date < not_none/date)}'
    'SELECT * from users WHERE enabled = 1 '

    >>> date = '2023-01-01'
    >>> f'SELECT * from users WHERE enabled = 1 {AND_(q.registration_date < not_none/date)}'
    'SELECT * from users WHERE enabled = 1 AND registration_date < ?'
    """
    return prefix_join('AND ', ' AND ', fragments)


def OR_(*fragments: Str) -> str:
    """Allows to make dynamic additions into existing static WHERE clause

    See `AND_` for usage.
    """
    return prefix_join('OR ', ' OR ', fragments)


def prefix_join(prefix: str, sep: str, fragments: t.Sequence[Str], wrap: t.Optional[str] = None) -> str:
    e = join_fragments(sep, fragments, wrap)
    return (prefix + e) if e else EMPTY


def WHERE(*fragments: Str) -> str:
    """WHERE concatenates not empty input with AND

    Could be used in context where all filters are static or dynamic
    to gracefully remove WHERE clause with empty filters.

    >>> name, age = None, None
    >>> f'SELECT * FROM users {WHERE(q.name == not_none/name, q.age > not_none/age)}'
    'SELECT * FROM users '

    >>> name, age = 'bob', 30
    >>> f'SELECT * FROM users {WHERE(q.name == not_none/name, q.age > not_none/age)}'
    'SELECT * FROM users WHERE name = ? AND age > ?'
    """
    return prefix_join('WHERE ', ' AND ', fragments)


def WITH(*fragments: Str) -> str:
    """Concatenates fragments with `,` and prepends WITH if not empty

    Could be used to add dynamic CTEs.

    >>> cte = ''
    >>> f'{WITH(cte)} SELECT * FROM users {WHERE(q.cond(cte, "name IN (SELECT name from cte_table)"))}'
    ' SELECT * FROM users '

    >>> cte = 'cte_table AS (SELECT name FROM banned)'
    >>> f'{WITH(cte)} SELECT * FROM users {WHERE(q.cond(cte, "name IN (SELECT name from cte_table)"))}'
    'WITH cte_table AS (SELECT name FROM banned) SELECT * FROM users WHERE name IN (SELECT name from cte_table)'
    """
    return prefix_join('WITH ', ', ', fragments)


def SET(*fragments: Str) -> str:
    return prefix_join('SET ', ', ', fragments)


def FIELDS(*fragments: Str) -> str:
    """Concatenates fragments with `,`

    >>> FIELDS('name', 'age')
    'name, age'
    """
    return join_fragments(', ', fragments)


def GROUP_BY(*fragments: Str) -> str:
    """Concatenates fragments with `,` and prepends GROUP BY if not empty

    >>> show_dates = True
    >>> GROUP_BY(q.name, q.cond(show_dates, 'date'))
    'GROUP BY name, date'

    >>> show_dates = False
    >>> GROUP_BY(q.name, q.cond(show_dates, 'date'))
    'GROUP BY name'
    """
    return prefix_join('GROUP BY ', ', ', fragments)


def ORDER_BY(*fragments: Str) -> str:
    """Concatenates fragments with `,` and prepends ORDER BY if not empty

    >>> sort_columns = [q.name, q.cond(True, 'date DESC')]
    >>> ORDER_BY(*sort_columns)
    'ORDER BY name, date DESC'

    >>> sort_columns = [q.name, q.cond(False, 'date DESC')]
    >>> ORDER_BY(*sort_columns)
    'ORDER BY name'
    """
    return prefix_join('ORDER BY ', ', ', fragments)


UNDEFINED = object()
EMPTY = Expr('')


class NotNone:
    """Conditional marker to mark None values as UNDEFINED objects

    UNDEFINED objects nullifies expression effect and could be used
    to construct dynamic queries.

    Most often used with QExpr operations.

    >>> q.field > not_none/None
    ''
    >>> q('field > {}', not_none/None)
    ''
    >>> q.eq(field=not_none/None)
    ''
    >>> q.IN('field', not_none/None)
    ''

    Dynamic query based on passed not none values:

    >>> age, name = 30, None
    >>> f'SELECT * FROM users WHERE enabled = 1 {AND_(q.age > not_none/age)} {AND_(q.name == not_none/name)}'
    'SELECT * FROM users WHERE enabled = 1 AND age > ? '
    """
    def __truediv__(self, other: t.Any) -> t.Any:
        if other is None:
            return UNDEFINED
        return other


not_none = NotNone()


class NotEmpty:
    """Conditional marker to mark empty (None, False, 0, empty containers) values as UNDEFINED objects

    UNDEFINED objects nullifies expression effect and could be used
    to construct dynamic queries.

    Most often used with QExpr operations.

    See NotNone usage
    """
    def __truediv__(self, other: t.Any) -> t.Any:
        if not other:
            return UNDEFINED
        return other


not_empty = NotEmpty()


class cond:
    """Conditional marker to mark values based on condition as UNDEFINED objects

    UNDEFINED objects nullifies expression effect and could be used
    to construct dynamic queries.

    Most often used with QExpr operations.

    >>> q.field > cond(False)/10
    ''

    >>> q.field > cond(True)/10
    'field > ?'

    Also see NotNone usage.
    """
    def __init__(self, cond: t.Any):
        self._cond = cond

    def __truediv__(self, other: t.Any) -> t.Any:
        if not self._cond:
            return UNDEFINED
        return other


def _in_range(q: 'QueryParams', field: Str, lop: str, left: t.Any, rop: str, right: t.Any) -> Expr:
    return AND(
        q.compile(f'{field} {lop} {{}}', (left,)) if left is not UNDEFINED else '',
        q.compile(f'{field} {rop} {{}}', (right,)) if right is not UNDEFINED else '',
    )


class QExpr:
    def __init__(self, q: 'QueryParams', value: str = ''):
        self.q = q
        self._sqlbind_value = value

    def __getattr__(self, name: str) -> 'QExpr':
        if self._sqlbind_value:
            return QExpr(self.q, f'{self._sqlbind_value}.{name}')
        return QExpr(self.q, name)

    def __call__(self, value: str) -> 'QExpr':
        return QExpr(self.q, value)

    def __str__(self) -> str:
        return self._sqlbind_value

    def __lt__(self, other: t.Any) -> Expr:
        return self.q(f'{self._sqlbind_value} < {{}}', other)

    def __le__(self, other: t.Any) -> Expr:
        return self.q(f'{self._sqlbind_value} <= {{}}', other)

    def __gt__(self, other: t.Any) -> Expr:
        return self.q(f'{self._sqlbind_value} > {{}}', other)

    def __ge__(self, other: t.Any) -> Expr:
        return self.q(f'{self._sqlbind_value} >= {{}}', other)

    def __eq__(self, other: t.Any) -> Expr:  # type: ignore[override]
        if other is None:
            return Expr(f'{self._sqlbind_value} IS NULL')
        return self.q(f'{self._sqlbind_value} = {{}}', other)

    def __ne__(self, other: t.Any) -> Expr:  # type: ignore[override]
        if other is None:
            return Expr(f'{self._sqlbind_value} IS NOT NULL')
        return self.q(f'{self._sqlbind_value} != {{}}', other)

    def __invert__(self) -> Expr:
        return Expr('NOT ' + self._sqlbind_value)

    def IN(self, other: t.Any) -> Expr:
        return self.q.IN(self._sqlbind_value, other)


class QExprDesc:
    def __get__(self, inst: t.Any, cls: t.Any) -> QExpr:
        assert inst is not None
        return QExpr(inst)


class QueryParams:
    """
    QueryParams accumulates query data and can be passed to actual
    `execute` later. QueryParams is a list or dictionary of values
    depending from used dialect. See `Dialect` for convenient way to
    get QueryParams instance.

    In general you should create new QueryParams instance for every
    constructed query.

    Most common usage patterns are:

    1) to bind (add) a value via `/` operator:

    >>> q = Dialect.default()
    >>> value = 10
    >>> f'SELECT * FROM table WHERE field = {q/value}'
    'SELECT * FROM table WHERE field = ?'
    >>> q
    [10]

    2) to bind a value with explicit template (note `{}` placeholder):

    >>> days_ago = 7
    >>> f'SELECT * FROM table WHERE {q("date > today() - {}", days_ago)}'
    'SELECT * FROM table WHERE date > today() - ?'

    3) to bind a value using `QExpr`, it allows to use comparison operators in "natural" way

    >>> start_date = '2023-01-01'
    >>> f'SELECT * FROM table WHERE {q.date > start_date}'
    'SELECT * FROM table WHERE date > ?'

    >>> q.name == 'Bob'  # unknown attribute access returns QExpr
    'name = ?'
    >>> q.users.name == 'Bob'  # any level of attributes could be used
    'users.name = ?'
    >>> q._.users.name == 'Bob'   # `_` provides an escape hatch to avoid conflicts with QueryParams methods/attributes
    'users.name = ?'
    >>> q._('LOWER(name)') == 'bob'  # `_()` call allow to use any literal as QExpr
    'LOWER(name) = ?'
    """
    dialect: t.Type['BaseDialect']
    _ = QExprDesc()

    def __getattr__(self, name: str) -> QExpr:
        return QExpr(self, name)

    def __truediv__(self, value: t.Any) -> Expr:
        return Expr(self.compile('{}', (value,)))

    def compile(self, expr: str, params: t.Sequence[t.Any]) -> str:
        raise NotImplementedError  # pragma: no cover

    def __call__(self, expr: str, *params: t.Any) -> Expr:
        """Binds provided params via template using `{}` placeholder

        >>> q('field BETWEEN {} AND {}', 10, 20)
        'field BETWEEN ? AND ?'
        >>> q
        [10, 20]
        """
        if any(it is UNDEFINED for it in params):
            return EMPTY
        return Expr(self.compile(expr, params))

    def cond(self, cond: t.Any, expr: Str, *params: t.Any) -> Expr:
        """Conditional binding

        >>> q.cond(False, 'enabled = 1')
        ''
        >>> q.cond(True, 'enabled = 1')
        'enabled = 1'
        """
        if cond:
            return Expr(self.compile(str(expr), params))
        return EMPTY

    def not_none(self, expr: Str, param: t.Optional[t.Any]) -> Expr:
        """Conditional binding based on param None-ness

        >>> q.not_none('field = {}', None)
        ''
        >>> q.not_none('field = {}', 10)
        'field = ?'
        """
        if param is not None:
            return Expr(self.compile(str(expr), (param,)))
        return EMPTY

    def not_empty(self, expr: Str, param: t.Optional[t.Any]) -> Expr:
        """Conditional binding based on param emptiness

        >>> q.not_empty('field IN {}', [])
        ''
        >>> q.not_none('field IN {}', [10, 20])
        'field IN ?'
        """
        if param:
            return Expr(self.compile(str(expr), (param,)))
        return EMPTY

    def IN(self, field: Str, values: t.Optional[t.List[t.Any]]) -> Expr:
        """Helper to abstract dealing with IN for different database backends

        >>> q = Dialect.default()
        >>> q.IN('field', [10, 20])
        'field IN ?'
        >>> q
        [[10, 20]]

        >>> q = Dialect.sqlite()  # sqlite can't bind whole arrays and all values should be unwrapped
        >>> q.IN('field', [10, 20])
        'field IN (?,?)'
        >>> q
        [10, 20]

        >>> q = Dialect.sqlite()            # also sqlite has a limit for number of parameters
        >>> q.IN('field', list(range(11)))  # after some threshold sqlbind render values inline
        'field IN (0,1,2,3,4,5,6,7,8,9,10)'
        >>> q
        []
        """
        if values is None or values is UNDEFINED:
            return EMPTY
        elif values:
            return self.dialect.IN(self, field, values)
        else:
            return Expr(self.dialect.FALSE)

    def eq(self, field__: t.Optional[Str] = None, value__: t.Any = None, **kwargs: t.Any) -> Expr:
        """Helper to generate equality comparisons

        >>> q.eq('field', 10)
        'field = ?'
        >>> q.eq('field', None)
        'field IS NULL'
        >>> q.eq(name='bob', age=30)
        '(name = ? AND age = ?)'
        >>> q.eq(**{'"weird field name"': 'value'})
        '"weird field name" = ?'
        """
        if field__:
            kwargs[str(field__)] = value__
        return AND(*(self.compile(f'{field} IS NULL', ())
                     if value is None
                     else self.compile(f'{field} = {{}}', (value,))
                     for field, value in kwargs.items()
                     if value is not UNDEFINED))

    def neq(self, field__: t.Optional[Str] = None, value__: t.Any = None, **kwargs: t.Any) -> Expr:
        """Opposite to `.eq`

        >>> q.neq(field=10, data=None)
        '(field != ? AND data IS NOT NULL)'
        """
        if field__:
            kwargs[str(field__)] = value__
        return AND(*(self.compile(f'{field} IS NOT NULL', ())
                     if value is None
                     else self.compile(f'{field} != {{}}', (value,))
                     for field, value in kwargs.items()
                     if value is not UNDEFINED))

    def in_range(self, field: Str, left: t.Any, right: t.Any) -> Expr:
        """Helper to check field is in [left, right) bounds

        >>> q.in_range('date', '2023-01-01', '2023-02-01')
        '(date >= ? AND date < ?)'
        >>> q
        ['2023-01-01', '2023-02-01']
        """
        return _in_range(self, field, '>=', left, '<', right)

    def in_crange(self, field: Str, left: t.Any, right: t.Any) -> Expr:
        """Helper to check field is in [left, right] bounds

        >>> q.in_crange('date', '2023-01-01', '2023-02-01')
        '(date >= ? AND date <= ?)'
        >>> q
        ['2023-01-01', '2023-02-01']
        """
        return _in_range(self, field, '>=', left, '<=', right)

    def WHERE(self, *cond: Str, **kwargs: t.Any) -> str:
        """Helper to render the whole WHERE part based on available conditions

        >>> value = None
        >>> f'SELECT * FROM table {q.WHERE(field=not_none/value)}'
        'SELECT * FROM table '

        >>> value = 10
        >>> f'SELECT * FROM table {q.WHERE(field=not_none/value)}'
        'SELECT * FROM table WHERE field = ?'
        """
        return WHERE(self.eq(**kwargs), *cond)

    def assign(self, **kwargs: t.Any) -> Expr:
        """Helper to render a sequence of assignments

        >>> q.assign(name='bob', age=30, confirmed_date=None)
        'name = ?, age = ?, confirmed_date = ?'
        """
        fragments = [self.compile(f'{field} = {{}}', (value,))
                     for field, value in kwargs.items()
                     if value is not UNDEFINED]
        return join_fragments(', ', fragments)

    def SET(self, **kwargs: t.Any) -> str:
        """Helper to render a SET clause

        >>> q.SET(name='bob', age=30, confirmed_date=None)
        'SET name = ?, age = ?, confirmed_date = ?'
        """
        return SET(self.assign(**kwargs))

    def VALUES(self, data: t.Optional[t.List[t.Dict[str, t.Any]]] = None, **kwargs: t.Any) -> str:
        """Helper to render field list and VALUES expression

        >>> data = [{'name': 'bob', 'age': 30}, {'name': 'fred', 'age': 20}]
        >>> f'INSERT INTO users {q.VALUES(data)}'
        'INSERT INTO users (name, age) VALUES (?, ?), (?, ?)'
        >>> q
        ['bob', 30, 'fred', 20]

        >>> f'INSERT INTO users {q.VALUES(name="bob", age=30)}'
        'INSERT INTO users (name, age) VALUES (?, ?)'
        """
        if not data:
            data = [kwargs]

        names = list(data[0].keys())
        params: t.List[t.Any] = []
        marks = '({})'.format(', '.join(['{}'] * len(names)))
        for it in data:
            params.extend(it[f] for f in names)

        return self.compile(f"({', '.join(names)}) VALUES {', '.join(marks for _ in range(len(data)))}", params)

    def LIMIT(self, value: t.Any) -> Expr:
        """Helper to render LIMIT

        value could be conditional

        >>> q.LIMIT(not_none/None)
        ''
        >>> q.LIMIT(10)
        'LIMIT ?'
        """
        return self('LIMIT {}', value)

    def OFFSET(self, value: t.Any) -> Expr:
        """Helper to render OFFSET

        value could be conditional

        >>> q.OFFSET(not_none/None)
        ''
        >>> q.OFFSET(10)
        'OFFSET ?'
        """
        return self('OFFSET {}', value)


class DictQueryParams(t.Dict[str, t.Any], QueryParams):
    def __init__(self, dialect: t.Type['BaseDialect']):
        dict.__init__(self, {})
        self.dialect = dialect
        self._count = 0

    def add(self, params: t.Sequence[t.Any]) -> t.List[str]:
        start = self._count
        self._count += len(params)
        names = [f'p{i}' for i, _ in enumerate(params, start)]
        self.update(zip(names, params))
        return names


class ListQueryParams(t.List[t.Any], QueryParams):
    def __init__(self, dialect: t.Type['BaseDialect']):
        list.__init__(self, [])
        self.dialect = dialect
        self._count = 0

    def add(self, params: t.Sequence[t.Any]) -> int:
        start = self._count
        self._count += len(params)
        self.extend(params)
        return start


class QMarkQueryParams(ListQueryParams):
    """QueryParams implementation for qmark (?) parameter style"""
    def compile(self, expr: str, params: t.Sequence[t.Any]) -> str:
        self.add(params)
        return expr.format(*('?' * len(params)))


class NumericQueryParams(ListQueryParams):
    """QueryParams implementation for numeric (:1, :2) parameter style"""
    def compile(self, expr: str, params: t.Sequence[t.Any]) -> str:
        start = self.add(params) + 1
        return expr.format(*(f':{i}' for i, _ in enumerate(params, start)))


class FormatQueryParams(ListQueryParams):
    """QueryParams implementation for format (%s) parameter style"""
    def compile(self, expr: str, params: t.Sequence[t.Any]) -> str:
        self.add(params)
        return expr.format(*(['%s'] * len(params)))


class NamedQueryParams(DictQueryParams):
    """QueryParams implementation for named (:name) parameter style"""
    def compile(self, expr: str, params: t.Sequence[t.Any]) -> str:
        names = self.add(params)
        return expr.format(*(f':{it}' for it in names))


class PyFormatQueryParams(DictQueryParams):
    """QueryParams implementation for pyformat (%(name)s) parameter style"""
    def compile(self, expr: str, params: t.Sequence[t.Any]) -> str:
        names = self.add(params)
        return expr.format(*(f'%({it})s' for it in names))


class BaseDialect:
    """Dialect compatible with most of backends"""
    FALSE = 'FALSE'

    @staticmethod
    def IN(q: QueryParams, field: Str, values: t.List[t.Any]) -> Expr:
        return q(f'{field} IN {{}}', values)


class SQLiteDialect(BaseDialect):
    """Dedicated SQLite dialiect to handle FALSE literal and IN operator"""
    FALSE = '0'

    @staticmethod
    def IN(q: QueryParams, field: Str, values: t.List[t.Any]) -> Expr:
        if len(values) > 10:
            # Trying to escape and assemble sql manually to avoid too many
            # parameters exception
            return Expr(f'{field} IN ({sqlite_value_list(values)})')
        else:
            qmarks = ','.join(['{}'] * len(values))
            return q(f'{field} IN ({qmarks})', *values)


def sqlite_escape(val: t.Union[float, int, str]) -> str:
    tval = type(val)
    if tval is str:
        return "'{}'".format(val.replace("'", "''"))  # type: ignore[union-attr]
    elif tval is int or tval is float:
        return str(val)
    raise ValueError(f'Invalid type: {val}')


def sqlite_value_list(values: t.List[t.Union[float, int, str]]) -> str:
    return ','.join(map(sqlite_escape, values))


class Dialect:
    """Namespace to hold most popular Dialect/QueryParams combinations"""
    def __init__(self, factory: t.Callable[[], QueryParams]):
        self.factory = factory

    def __get__(self, inst: t.Any, cls: t.Any) -> QueryParams:
        return self.factory()

    @staticmethod
    def default() -> QueryParams:
        """Uses qmarks (?) as placeholders

        >>> q = Dialect.default()
        >>> f'field = {q/20}'
        'field = ?'
        """
        return QMarkQueryParams(BaseDialect)

    @staticmethod
    def default_named() -> QueryParams:
        """Uses named params (:param) as placeholders.

        Backend examples: SQLAlchemy

        >>> q = Dialect.default_named()
        >>> f'field = {q/20}'
        'field = :p0'
        """
        return NamedQueryParams(BaseDialect)

    @staticmethod
    def default_pyformat() -> QueryParams:
        """Uses pyformat params (%(param)s) as placeholders.

        Backend examples: psycopg2 and clickhouse-driver

        >>> q = Dialect.default_pyformat()
        >>> f'field = {q/20}'
        'field = %(p0)s'
        """
        return PyFormatQueryParams(BaseDialect)

    @staticmethod
    def default_format() -> QueryParams:
        """Uses format params (%s) as placeholders.

        Backend examples: psycopg2 and mysql-connector-python

        >>> q = Dialect.default_format()
        >>> f'field = {q/20}'
        'field = %s'
        """
        return FormatQueryParams(BaseDialect)

    @staticmethod
    def sqlite() -> QueryParams:
        """Uses sqlite dialect and renders binds with qmark (?) placeholders"""
        return QMarkQueryParams(SQLiteDialect)

    @staticmethod
    def sqlite_named() -> QueryParams:
        """Uses sqlite dialect and renders binds with named (:param) placeholders"""
        return NamedQueryParams(SQLiteDialect)
