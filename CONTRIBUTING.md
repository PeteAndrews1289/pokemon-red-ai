# Contributing

Early contributions should focus on deterministic emulator control, observation validation, tests,
and reproducible documentation.

Before opening a change:

```bash
python scripts/check_private_artifacts.py
ruff check .
pytest -m "not integration"
```

Never commit ROMs, save files, emulator snapshots, credentials, absolute private paths, recordings,
or generated checkpoints. Describe new observation fields and reward signals in the experiment
protocol, and include tests for any new emulator behavior.
