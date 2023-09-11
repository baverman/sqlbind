import typing as t


class Expr(str):
    def __or__(self, other: str) -> 'Expr':
        return OR(self, other)

    def __and__(self, other: str) -> 'Expr':
        return AND(self, other)


def join_fragments(sep: str, fragments: t.Sequence[str], wrap: t.Optional[str] = None) -> Expr:
    fragments = list(filter(None, fragments))
    if not fragments:
        return EMPTY
    elif len(fragments) == 1:
        return Expr(fragments[0])

    e = sep.join(fragments)
    if wrap:
        e = wrap.format(e)
    return Expr(e)


def OR(*fragments: str) -> Expr:
    return join_fragments(' OR ', fragments, '({})')


def AND(*fragments: str) -> Expr:
    return join_fragments(' AND ', fragments, '({})')


def prefix_join(prefix: str, sep: str, fragments: t.Sequence[str], wrap: t.Optional[str] = None) -> str:
    e = join_fragments(sep, fragments, wrap)
    return (prefix + e) if e else EMPTY


def WHERE(*fragments: str) -> str:
    return prefix_join('WHERE ', ' AND ', fragments)


def WITH(*fragments: str) -> str:
    return prefix_join('WITH ', ', ', fragments)


def SET(*fragments: str) -> str:
    return prefix_join('SET ', ', ', fragments)


def FIELDS(*fragments: str) -> str:
    return join_fragments(', ', fragments)


EMPTY = Expr('')


class QueryParams:
    dialect: t.Type['BaseDialect']

    def compile(self, expr: str, params: t.Sequence[t.Any]) -> str:
        raise NotImplementedError  # pragma: no cover

    def __call__(self, expr: str, *params: t.Any) -> Expr:
        return Expr(self.compile(expr, params))

    def cond(self, cond: t.Any, expr: str, *params: t.Any) -> Expr:
        if cond:
            return Expr(self.compile(expr, params))
        return EMPTY

    def not_none(self, expr: str, param: t.Optional[t.Any]) -> Expr:
        if param is not None:
            return Expr(self.compile(expr, (param,)))
        return EMPTY

    def is_true(self, expr: str, param: t.Optional[t.Any]) -> Expr:
        if param:
            return Expr(self.compile(expr, (param,)))
        return EMPTY

    def IN(self, field: str, values: t.Optional[t.List[t.Any]]) -> Expr:
        if values is None:
            return EMPTY
        elif values:
            return self.dialect.IN(self, field, values)
        else:
            return Expr(self.dialect.FALSE)

    def eq(self, field: t.Optional[str] = None, value: t.Any = None, **kwargs: t.Any) -> Expr:
        if field:
            kwargs[field] = value
        return AND(*(self.compile(f'{field} is NULL', ())
                     if value is None
                     else self.compile(f'{field} = {{}}', (value,))
                     for field, value in kwargs.items()))

    def neq(self, field: t.Optional[str] = None, value: t.Any = None, **kwargs: t.Any) -> Expr:
        if field:
            kwargs[field] = value
        return AND(*(self.compile(f'{field} is not NULL', ())
                     if value is None
                     else self.compile(f'{field} != {{}}', (value,))
                     for field, value in kwargs.items()))

    def WHERE(self, *cond: str, **kwargs: t.Any) -> str:
        return WHERE(self.eq(**kwargs), *cond)

    def set(self, **kwargs: t.Any) -> Expr:
        fragments = [self.compile(f'{field} = {{}}', (value,))
                     for field, value in kwargs.items()]
        return join_fragments(', ', fragments)

    def SET(self, **kwargs: t.Any) -> str:
        return SET(self.set(**kwargs))

    def VALUES(self, data: t.Optional[t.List[t.Dict[str, t.Any]]] = None, **kwargs: t.Any) -> str:
        if not data:
            data = [kwargs]

        names = list(data[0].keys())
        params: t.List[t.Any] = []
        marks = '({})'.format(', '.join(['{}'] * len(names)))
        for it in data:
            params.extend(it[f] for f in names)

        return self.compile(f"({', '.join(names)}) VALUES {', '.join(marks for _ in range(len(data)))}", params)


class DictQueryParams(dict, QueryParams):
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


class ListQueryParams(list, QueryParams):
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
    def compile(self, expr: str, params: t.Sequence[t.Any]) -> str:
        self.add(params)
        return expr.format(*('?' * len(params)))


class NumericQueryParams(ListQueryParams):
    def compile(self, expr: str, params: t.Sequence[t.Any]) -> str:
        start = self.add(params) + 1
        return expr.format(*(f':{i}' for i, _ in enumerate(params, start)))


class FormatQueryParams(ListQueryParams):
    def compile(self, expr: str, params: t.Sequence[t.Any]) -> str:
        self.add(params)
        return expr.format(*(['%s'] * len(params)))


class NamedQueryParams(DictQueryParams):
    def compile(self, expr: str, params: t.Sequence[t.Any]) -> str:
        names = self.add(params)
        return expr.format(*(f':{it}' for it in names))


class PyFormatQueryParams(DictQueryParams):
    def compile(self, expr: str, params: t.Sequence[t.Any]) -> str:
        names = self.add(params)
        return expr.format(*(f'%({it})s' for it in names))


class BaseDialect:
    FALSE = 'FALSE'

    @staticmethod
    def IN(q: QueryParams, field: str, values: t.List) -> Expr:
        return q(f'{field} IN {{}}', values)


class SQLiteDialect(BaseDialect):
    FALSE = '0'

    @staticmethod
    def IN(q: QueryParams, field: str, values: t.List) -> Expr:
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
    @staticmethod
    def default() -> QueryParams:
        return QMarkQueryParams(BaseDialect)

    @staticmethod
    def default_pyformat() -> QueryParams:
        return PyFormatQueryParams(BaseDialect)

    @staticmethod
    def default_format() -> QueryParams:
        return FormatQueryParams(BaseDialect)

    @staticmethod
    def sqlite() -> QueryParams:
        return QMarkQueryParams(SQLiteDialect)

    @staticmethod
    def sqlite_named() -> QueryParams:
        return NamedQueryParams(SQLiteDialect)
