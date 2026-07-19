# Contributing

Early contributions should focus on deterministic emulator control, observation validation, tests,
and reproducible documentation.

Before opening a change:

```bash
python scripts/check_private_artifacts.py
python scripts/check_docs.py
ruff check .
pytest -m "not integration"
```

Never commit ROMs, save files, emulator snapshots, credentials, absolute private paths, recordings,
or generated checkpoints. Describe new observation fields and reward signals in the experiment
protocol, and include tests for any new emulator behavior.

Use the [experiment record template](docs/experiment-template.md) for results and the
[agent card template](docs/agent-card-template.md) when a policy, prompt, model, observation, or
memory rule changes. Documentation is part of the experiment: retain failures, label illustrative
examples, and make the evidence understandable without requiring readers to inspect source code.
