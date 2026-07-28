# Security Policy

## Supported version

This repository is a completed research record. Security and reproducibility fixes are supported
on `main`; historical experiment branches, tags, and external run artifacts are preserved as
evidence and are not maintained as active releases.

## Reporting a vulnerability

Please use GitHub's
[private vulnerability reporting](https://github.com/PeteAndrews1289/pokemon-red-ai/security/advisories/new)
for vulnerabilities involving the harness, artifact validation, checkpoint handling, command-line
interfaces, or CI.

Do not include a ROM, save file, emulator snapshot, model checkpoint, credential, private machine
path, or unredacted runtime trace in a report. Describe the issue with the smallest synthetic
fixture that reproduces it.

Useful reports include:

- a path that bypasses the private-artifact publication guard;
- unsafe loading or deserialization of an untrusted checkpoint or run record;
- command or path injection through a CLI argument;
- an integrity check that accepts a modified ROM, checkpoint, or evidence file;
- a boundary violation that lets trainer-only state choose or replace an evaluated action; or
- a CI or documentation path that publishes proprietary or sensitive artifacts.

## Research boundary

Hashes in this project provide identity and integrity checks; they are not digital signatures and
do not authenticate an author. The emulator and learning dependencies process user-supplied local
files, so only lawfully obtained, trusted game and checkpoint files should be used.
