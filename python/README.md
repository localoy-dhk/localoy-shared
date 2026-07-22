# localoy-shared (Python)

Generated Python distribution of the canonical Localoy enums. **Do not edit
`localoy_shared/enums.py` by hand** — it is generated from `enums.json` at the
repo root by `generate.py`.

Install from a tag:

```bash
pip install "git+https://github.com/localoy-dhk/localoy-shared@v0.1.0#subdirectory=python"
```

Use:

```python
from localoy_shared import EventStatus

EventStatus.PUBLISHED.value  # "published"
```

Full docs: [repo README](https://github.com/localoy-dhk/localoy-shared#readme).
