# Contributing

> **Maintenance status:** the research program is concluded. Contributions should focus on
> security, reproducibility, compatibility, tests, or corrections to the published record. New
> agent architectures and experiments should begin as a separately declared successor project so
> the frozen V12 result and its claim boundary remain intact.

Before opening a change:

```bash
python scripts/check_private_artifacts.py
python scripts/check_docs.py
ruff check .
pytest -m "not integration"
```

Never commit ROMs, save files, emulator snapshots, credentials, absolute private paths, recordings,
or generated checkpoints. In the primary blind track, rendered pixels and the actor's own action
history are the only policy channels; reward must be derived from those same inputs. RAM, tile data,
OCR, referee fields, start-state selection, and checkpoint selection can all leak information even
when absent from the observation vector. Describe every new channel and reward in the experiment
protocol and include an independence test.

Use the [experiment record template](docs/experiment-template.md) for results and the
[agent card template](docs/agent-card-template.md) when a policy, prompt, model, observation, or
memory rule changes. Documentation is part of the experiment: retain failures, label illustrative
examples, and make the evidence understandable without requiring readers to inspect source code.
