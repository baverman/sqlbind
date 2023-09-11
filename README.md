# sqlbind

Lightweight text-based SQL parameter binds

```python
import sqlite3
from sqlbind import Dialect, WHERE

conn = sqlite3.connect(':memory:')
with conn:
    conn.execute('CREATE TABLE t(name TEXT, age INTEGER)')

    q = Dialect.sqlite()
    data = [{'name': 'boo', 'age': 20}]
    conn.execute(f'INSERT INTO t {q.VALUES(data)}', q)

    q = Dialect.sqlite()
    conn.execute(f'INSERT INTO t {q.VALUES(name="bar", age=30)}', q)

    q = Dialect.sqlite()
    conn.execute(f'UPDATE t {q.SET(age=45)} {q.WHERE(name="boo")}', q)

q = Dialect.sqlite_named()  # dict based query params could be shared
assert conn.execute(f'SELECT age FROM t {q.WHERE(name="boo")}', q).fetchall() == [(45,)]
assert conn.execute(f'SELECT * FROM t {WHERE(q.neq(name="boo"))}', q).fetchall() == [('bar', 30)]
```
