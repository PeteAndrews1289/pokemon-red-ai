from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pokemon_red_ai.constants import SupportedRom
from pokemon_red_ai.rom import RomValidationError, fingerprint_rom, verify_rom


def test_fingerprint_rom_reads_title_and_hashes(tmp_path: Path) -> None:
    contents = bytearray(0x200)
    contents[0x134:0x13F] = b"POKEMON RED"
    rom_path = tmp_path / "fixture.bin"
    rom_path.write_bytes(contents)

    fingerprint = fingerprint_rom(rom_path)

    assert fingerprint.filename == "fixture.bin"
    assert fingerprint.title == "POKEMON RED"
    assert fingerprint.size_bytes == len(contents)
    assert fingerprint.sha1 == hashlib.sha1(contents, usedforsecurity=False).hexdigest()
    assert fingerprint.sha256 == hashlib.sha256(contents).hexdigest()


def test_verify_rom_accepts_exact_expected_fingerprint(tmp_path: Path) -> None:
    contents = bytearray(0x200)
    contents[0x134:0x13F] = b"POKEMON RED"
    rom_path = tmp_path / "fixture.bin"
    rom_path.write_bytes(contents)
    fingerprint = fingerprint_rom(rom_path)
    expected = SupportedRom(
        title=fingerprint.title,
        size_bytes=fingerprint.size_bytes,
        sha1=fingerprint.sha1,
        sha256=fingerprint.sha256,
    )

    assert verify_rom(rom_path, expected) == fingerprint


def test_verify_rom_rejects_mismatch(tmp_path: Path) -> None:
    rom_path = tmp_path / "wrong.bin"
    rom_path.write_bytes(bytes(0x200))
    expected = SupportedRom(title="EXPECTED", size_bytes=1, sha1="a", sha256="b")

    with pytest.raises(RomValidationError, match="Unsupported ROM revision"):
        verify_rom(rom_path, expected)


def test_public_fingerprint_omits_absolute_path(tmp_path: Path) -> None:
    rom_path = tmp_path / "fixture.bin"
    rom_path.write_bytes(bytes(0x200))

    public = fingerprint_rom(rom_path).public_dict()

    assert "path" not in public
    assert "filename" not in public
    assert str(tmp_path) not in str(public)
