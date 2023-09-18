# sqlbind

**sqlbind** allows to bind parameters in text based raw SQL queries.

```python
>>> q = sqlbind.Dialect.default()
>>> email = 'some@domain.com'
>>> sql = f'SELECT * FROM users WHERE email = {q/email}'
>>> sql
'SELECT * FROM users WHERE email = ?'
>>> q
['some@domain.com']
>>> data = conn.execute(sql, q)

```

Supports all [DBAPI parameter styles][dbapi]. Isn't limited by DBAPI compatible drivers and
could be used with anything accepting raw SQL query and parameters in some way. For example
**sqlbind** could be used with [SQLAlchemy textual queries][sqa-text]. Or with [clickhouse-driver][ch]'s
non-DBAPI interface.

[dbapi]: https://peps.python.org/pep-0249/#paramstyle
[sqa-text]: https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.text
[ch]: https://clickhouse-driver.readthedocs.io/en/latest/quickstart.html#selecting-data


## Installation

```
pip install sqlbind
```


## Motivation

ORMs are great and could be used effectively for a huge number of tasks. But
after many years with SQLAlchemy I've noticed some repeating patterns:

* It's really not an easy task to decipher complex SQLAlchemy expression back into SQL.
  Especially when CTEs, sub-queries, nested queries or self-referential queries
  are involved. It composes quite well but it takes too much effort to write
  and read SQLAlchemy queries. For novices it could be a hard time to deal
  with it.

* Most of reporting queries are big enough already not to be bothered with ORMs and
  use raw SQL anyway. This kind of SQL often requires dynamic constructs and becomes
  string fiddling contraption.

* For a few tasks ORMs bring too much overhead and the only solution is to get
  down to raw DBAPI connection and raw SQL.

* (*Minor personal grudge, please ignore it*) For some ORMs (like Django ORM) your
  SQL intuition could be useless and even doesn't work.

It boils down to one thing: from time to time you have to write raw
SQL queries. I could highlight 3 types of queries:

1. Fixed queries. They don't contain any parameters. For example
   `SELECT id, name FROM users ORDER BY registered DESC LIMIT 10`.
   In general fixed queries or fixed query parts compose well and don't require any
   special treatment. Python's f-strings are enough.

2. Static queries. They contain parameters but structure is fully known beforehand.
   For example `SELECT id, name FROM users WHERE email = :email LIMIT 1`. They
   are also could be composed without large issues, especially for connection
   drivers supporting named parameters (`:param`, `%(param)s`) and accepting dicts as parameters.
   Although for positional connection drivers (`%s`, `?`) composition requires careful
   parameter tracking and queries could be fragile to change.

3. Dynamic queries. Query part presence could depend on parameter value or
   external condition. For example to provide result on input filter you have
   to add CTE and corresponding JOIN to a query. Or add filters only for non
   `None` input values. ORMs are effective for composing such queries. Using
   raw SQL are almost impossible for abstraction and leads to a complex
   boilerplate heavy source code.

Note: here and in following sections I deliberately use simple examples. In real life
there is no need to use **sqlbind** for such kind of queries.

Note: by composing I mean ability to assemble a final query from parts which could be
abstracted and reused.

**sqlbind** tries to address issues with static and dynamic query types. It tracks
parameter binds and could help with dynamic query parts.


## Quick start

Some things to consider:

* **sqlbind** tries to provide an API for a simple composition of raw SQL. Most
  operations return string-like objects ready to be inserted in the final query.
  **sqlbind** does trivial things and is easy to reason about.

* There is a large set of functions/methods to address dynamic queries but you
  haven't use it inline in a single query string. You could use variables to
  keep query parts and stitch resulted SQL from these parts.

* This README misses large portions of API. Feel free to explore doc strings
  with examples of fully strictly type-hinted **sqlbind**'s source code!

General use case looks like:

```python
# a global alias to dialect used by connection backend
QParams = sqlbind.Dialect.some_dialect

def get_my_data(value1, value2):
    # Construct empty fresh sqlbind.QueryParams()
    q = QParams()

    # Use `q` to bind parameter values used in SQL.
    sql = f'SELECT * FROM table WHERE field1 = {q/value1} AND field2 > {q/value2}'

    # Pass query and parameters into execute
    return get_connection().execute(sql, q).fetchall()
```


## Static queries

For queries or query parts with a known structure the most simple way to bind a parameter is to
use bind operator `/`:

```python
>>> value = 10
>>> q = sqlbind.Dialect.default()
>>> q/value
'?'
>>> q
[10]

```

It returns a placeholder for a corresponding dialect and adds parameter's value to
`q` object. That's basically all.

```python
>>> date = "2023-01-01"
>>> q = sqlbind.Dialect.default_named()
>>> f'SELECT * FROM users WHERE registered > {q/date}'
'SELECT * FROM users WHERE registered > :p0'
>>> q
{'p0': '2023-01-01'}

```

Note: there is no much value in **sqlbind** if you have only static
queries and use connection backends accepting named parameters.


## Dynamic queries

Here begins a fun part. We can't use simple binds for dynamic queries.
For example we have a function returning recently registered users:

```python
def get_fresh_users(registered_from: datetime):
    q = QParams()  # an alias to some dialect to construct sqlbind.QueryParams instance
    sql = f'''\
        SELECT * FROM users
        WHERE registered > {q/registered_from}
        ORDER BY registered
    '''
    return conn.execute(sql, q)
```

And later there is a new requirement for the function. It should return only
enabled or only disabled users if corresponding argument is passed.

```python
def get_fresh_users(registered_from: datetime, enabled: Optional[bool] = None):
    q = QParams()

    if enabled is not None:
        enabled_filter = f' AND enabled = {q/enabled}'
    else:
        enabled_filter = ''

    sql = f'''\
        SELECT * FROM users
        WHERE registered > {q/registered_from} {enabled_filter}
        ORDER BY registered
    '''
    return conn.execute(sql, q)
```

It looks almost pretty. See how `q/enabled` helped to track additional parameter.
But you can predict where we are going. Another one or two
additional filters and it would be a complete mess. Take note how `WHERE` lost `AND`
between two filters.


### q-templates

In reality bind operator `/` is a sugar on top of generic **sqlbind**'s API to
bind parameters via q-templates.

```python
>>> q = sqlbind.Dialect.default()
>>> q('field BETWEEN {} AND {}', 10, 20)
'field BETWEEN ? AND ?'
>>> q
[10, 20]

```

`QueryParams` `q` object is also a callable accepting a template with `{}`
placeholders and following parameters to substitute. `q/value` is same as calling
`q('{}', value)`

```python
>>> q/10
'?'
>>> q('{}', 10)
'?'

```

You could use q-templates to bind parameters in complex SQL expressions.


### Conditionals

`q.cond`, `q.not_none` and `q.not_empty` could render a q-template as an empty
string based on input parameters.

```python
>>> enabled = True
>>> q.cond(enabled is not None, ' AND enabled = {}', enabled)
' AND enabled = ?'
>>> enabled = None
>>> q.cond(enabled is not None, ' AND enabled = {}', enabled)
''

```

`q.cond` is a generic form. To remove a repetition (`enabled is not
None`/`enabled`) when value is used both in a condition and as a parameter
value there are two helpers for most common cases. Check value is not None
(`q.not_none`) and value is not empty (`bool(value)` is True):

```python
>>> enabled = True
>>> q.not_none(' AND enabled = {}', enabled)
' AND enabled = ?'
>>> enabled = None
>>> q.not_none(' AND enabled = {}', enabled)
''

```

Let's try it in the function:

```python
def get_fresh_users(registered_from: datetime, enabled: Optional[bool] = None):
    q = QParams()

    enabled_filter = q.not_none(' AND enabled = {}', enabled)

    sql = f'''\
        SELECT * FROM users
        WHERE registered > {q/registered_from} {enabled_filter}
        ORDER BY registered
    '''
    return conn.execute(sql, q)
```

Hmm. But really nothing was changed. You could write previous code with ternary
if/else and it would look the same from semantic standpoint. May be use it
inline?


```python
def get_fresh_users(registered_from: datetime, enabled: Optional[bool] = None):
    q = QParams()

    sql = f'''\
        SELECT * FROM users
        WHERE registered > {q/registered_from}
              {q.not_none(' AND enabled = {}', enabled)}
        ORDER BY registered
    '''
    return conn.execute(sql, q)
```

Ugh. Abomination, to say at least.

* `AND` in the middle of a cryptic expression.
* `q.not_none` and `enabled` is far away and it's not obvious they are connected
* expression is too long and noisy

Let's tackle issues bit by bit.


### `AND_`/`OR_` prependers

Prependers could render not empty inputs with corresponding prefixes and empty
string otherwise.

```python
>>> AND_('field1 > 1', 'field2 < 1')
'AND field1 > 1 AND field2 < 1'
>>> OR_('field1 > 1', 'field2 < 1')
'OR field1 > 1 OR field2 < 1'
>>> AND_(q.not_none('enabled = {}', True))
'AND enabled = ?'
>>> AND_(q.not_none('enabled = {}', None))
''

```

Our function with prependers:

```python
from sqlbind import AND_

def get_fresh_users(registered_from: datetime, enabled: Optional[bool] = None):
    q = QParams()

    sql = f'''\
        SELECT * FROM users
        WHERE registered > {q/registered_from}
              {AND_(q.not_none('enabled = {}', enabled))}
        ORDER BY registered
    '''
    return conn.execute(sql, q)
```

At least AND is almost on it's place in SQL structure.


### Conditional markers

Conditional markers `not_none`/`not_empty`/`cond` allows to tie conditional property with variable itself.

```python
>>> not_none/10
10
>>> not_none/None is sqlbind.UNDEFINED  # returns special UNDEFINED object
True
>>> q('enabled = {}', not_none/10)
'enabled = ?'
>>> q('enabled = {}', not_none/None)  # UNDEFINED parameters force expression to be rendered as empty
''

```

`sqlbind.not_empty` is the same as `sqlbind.not_none` but checks for value trueness. `sqlbind.cond` is
almost always awkward to use inline in real life and exists largely for symmetry.

Rewritten function:

```python
from sqlbind import AND_, not_none

def get_fresh_users(registered_from: datetime, enabled: Optional[bool] = None):
    q = QParams()

    sql = f'''\
        SELECT * FROM users
        WHERE registered > {q/registered_from}
              {AND_(q('enabled = {}', not_none/enabled))}
        ORDER BY registered
    '''
    return conn.execute(sql, q)
```

Almost there.


### q-expressions

Any unknown attribute access to `q` object returns `QExpr` which has str
conversion as an attribute name:

```python
>>> str(q.field)
'field'
>>> str(q.table.field)
'table.field'
>>> str(q._.cond)  # to resolve conflicting names, you could use `q._.`(stare operator)
'cond'
>>> str(q._('"weird table"."weird column"'))  # or `q._`(pirate operator) to use any string
'"weird table"."weird column"'

```

q-expressions know about parent `q` object and define a number of infix operators
allowing to bind a right parameter.

```python
>>> q.field > 10
'field > ?'
>>> q.table.field == 20
'table.field = ?'
>>> q._.table.field == None
'table.field IS NULL'
>>> q._('"my column"') != None
'"my column" IS NOT NULL'
>>> q.field <= not_none/None  # conditional marks also works!
''
>>> q.field.IN(not_none/[10]) # BTW sqlbind has workaround for SQLite to deal with arrays in IN
'field IN ?'

```

It could look like a hack and fill ORMish but there is no any
expression trees and tree compilation passes. q-expressions
are immediately rendered as strings and simple to reason about.

Let's use q-expressions with the function:

```python
from sqlbind import AND_, not_none

def get_fresh_users(registered_from: datetime, enabled: Optional[bool] = None):
    q = QParams()

    sql = f'''\
        SELECT * FROM users
        WHERE registered > {q/registered_from}
              {AND_(q.enabled == not_none/enabled)}
        ORDER BY registered
    '''
    return conn.execute(sql, q)
```

I have no any other tricks. It's the final inline version. I can't make it
more pretty and readable.


### WHERE prepender

But we could extract filters outside of f-strings and use `sqlbind.WHERE`
prepender. It could help with readability of long complex filters.

```python
from sqlbind import not_none, WHERE

def get_fresh_users(registered_from: datetime, enabled: Optional[bool] = None):
    q = QParams()

    filters = [
        q.registered > registered_from,
        q.enabled == not_none/enabled,
    ]

    sql = f'SELECT * FROM users {WHERE(*filters)} ORDER BY registered'
    return conn.execute(sql, q)
```

Or you could use `&` operator to join filters without list:

```python
>>> filters = (q.registered > '2023-01-01') & (q.enabled == not_none/True)
>>> WHERE(filters)
'WHERE (registered > ? AND enabled = ?)'

```

— "Wait a minute. You said there is no expression trees and compilation! And
all operations return strings!"


### Expressions

I lied. Almost all methods and functions return `sqlbind.Expr`. It's a very shallow
descendant of `str` with only `__or__`, `__and__` and `__invert__`
reimplemented.

```python
>>> q('enabled') & q('registered')
'(enabled AND registered)'
>>> type(q('enabled'))
<class 'sqlbind.Expr'>
>>> type(q.enabled == True)
<class 'sqlbind.Expr'>

```

All Expr instances could be composed with `&`, `|` and `~` (negate) operations.
Sadly due to python's' precedence rules you have to wrap expressions into
additional parens to make it work.


### Conclusion

I kept promise you always deal with strings!
