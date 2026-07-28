## What changed

Describe the behavior, documentation, or experiment being added.

## Why

Explain the question this change answers or the failure it prevents.

## Evidence

- [ ] Relevant unit tests pass
- [ ] Private-ROM integration tests pass when emulator behavior changed
- [ ] `python scripts/check_private_artifacts.py` passes
- [ ] `python scripts/check_docs.py` passes
- [ ] `ruff check .` passes

List commands, experiment IDs, or trace hashes here.

## Reproducibility and privacy

- [ ] No ROM, save, snapshot, checkpoint, gameplay capture, or secret is committed
- [ ] No private absolute path appears in code, docs, fixtures, or traces
- [ ] New observation fields and reward terms are documented
- [ ] Human interventions and invalid runs are disclosed
- [ ] Claims such as “autonomous,” “screen-only,” or “learned” match the protocol

## Visual review

- [ ] Diagrams render on GitHub
- [ ] Charts label axes, units, denominators, and evaluation points
- [ ] Visuals distinguish measured results from plans or illustrative examples
