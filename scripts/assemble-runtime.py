#!/usr/bin/env python3
"""Create a model-free Decky runtime from upstream Linux package archives."""
from __future__ import annotations

import argparse
import shutil
import tarfile
import tempfile
from pathlib import Path

KEEP = ("dlssnr-amd", "reshade", "model-tools", "ini")


def safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.getmembers():
        target = (root / member.name).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"unsafe archive member: {member.name}")
    archive.extractall(destination, filter="data")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    shutil.rmtree(output, ignore_errors=True)
    for archive in args.archives:
        name = archive.name
        architecture = "x86_64" if "x86_64" in name else "x86" if "i686" in name else None
        if not architecture:
            raise ValueError(f"cannot determine architecture: {archive}")
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            with tarfile.open(archive, "r:gz") as tar:
                safe_extract(tar, root)
            if any(path.name == "dlssnr.bin" for path in root.rglob("dlssnr.bin")):
                raise ValueError("refusing to package an NVIDIA model")
            destination = output / architecture
            for relative in KEEP:
                source = root / relative
                if not source.exists():
                    raise ValueError(f"upstream package missing {relative}")
                shutil.copytree(source, destination / relative, dirs_exist_ok=True)
    if any(path.name == "dlssnr.bin" for path in output.rglob("dlssnr.bin")):
        raise ValueError("model exclusion check failed")


if __name__ == "__main__":
    main()
