# Requirements

```
pip install twine build
```

# Build

```
python -m build -nw  .
```

# Upload

```
TWINE_PASSWORD="$(pass dev/pypy-tokens/all)" twine upload -u __token__ dist/<package>
```
