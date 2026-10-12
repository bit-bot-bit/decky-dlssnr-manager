"""Decky backend for a reversible, user-confirmed DLSSNR ReShade install.

It intentionally does not ship, download, or retain NVIDIA's DLL/model.  A user
must select their own local copy when installing; extraction happens locally.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import decky

MODEL_NAME = "nvngx_dlssnr.dll"
MANIFEST_VERSION = 1
EDITABLE = {
    "Enabled", "WorkingScale", "Passes", "Exposure", "ExposureBias",
    "Curve", "Contrast", "Saturation", "Sound",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def vdf_value(text: str, key: str) -> str:
    match = re.search(rf'"{re.escape(key)}"\s+"((?:\\.|[^"\\])*)"', text)
    return bytes(match.group(1), "utf-8").decode("unicode_escape") if match else ""


def pe_architecture(path: Path) -> str | None:
    try:
        with path.open("rb") as source:
            if source.read(2) != b"MZ":
                return None
            source.seek(0x3C)
            offset = struct.unpack("<I", source.read(4))[0]
            source.seek(offset + 4)
            machine = struct.unpack("<H", source.read(2))[0]
    except (OSError, struct.error):
        return None
    return {0x14C: "x86", 0x8664: "x86_64"}.get(machine)


class Plugin:
    def _root(self) -> Path:
        return Path(decky.DECKY_PLUGIN_DIR).resolve()

    def _data(self) -> Path:
        root = Path(decky.DECKY_PLUGIN_RUNTIME_DIR).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _manifest_path(self, appid: str) -> Path:
        path = self._data() / "installs" / f"{appid}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _read_manifest(self, appid: str) -> dict[str, Any] | None:
        path = self._manifest_path(appid)
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if value.get("format") == MANIFEST_VERSION else None
        except (OSError, ValueError):
            return None

    def _steam_roots(self) -> list[Path]:
        home = Path(getattr(decky, "DECKY_USER_HOME", decky.HOME)).expanduser()
        candidates = [home / ".local/share/Steam", home / ".steam/steam", home / ".steam/root"]
        roots: list[Path] = []
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.is_dir() and resolved not in roots:
                roots.append(resolved)
        for root in list(roots):
            file = root / "steamapps/libraryfolders.vdf"
            if not file.is_file():
                continue
            for encoded in re.findall(r'"path"\s+"((?:\\.|[^"\\])*)"', file.read_text(encoding="utf-8", errors="replace")):
                path = Path(bytes(encoded, "utf-8").decode("unicode_escape")).expanduser().resolve()
                if path.is_dir() and path not in roots:
                    roots.append(path)
        return roots

    def _games(self) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for root in self._steam_roots():
            apps = root / "steamapps"
            if not apps.is_dir():
                continue
            for manifest in apps.glob("appmanifest_*.acf"):
                text = manifest.read_text(encoding="utf-8", errors="replace")
                appid = vdf_value(text, "appid")
                install_dir = vdf_value(text, "installdir")
                name = vdf_value(text, "name")
                game = (apps / "common" / install_dir).resolve()
                if appid and name and game.is_dir() and str(game).startswith(str((apps / "common").resolve()) + os.sep):
                    found[appid] = {"appid": appid, "name": name, "install_dir": str(game)}
        return sorted(found.values(), key=lambda game: game["name"].casefold())

    def _game(self, appid: str) -> dict[str, Any]:
        if not appid.isdigit():
            raise ValueError("invalid Steam app ID")
        for game in self._games():
            if game["appid"] == appid:
                return game
        raise ValueError("installed Steam game was not found")

    def _targets(self, game: dict[str, Any]) -> list[dict[str, str]]:
        root = Path(game["install_dir"]).resolve()
        result: list[dict[str, str]] = []
        ignored = ("crashreport", "easyanticheat", "eac", "uninstall", "setup", "launcher", "redist")
        for executable in root.rglob("*.exe"):
            if len(result) >= 80:
                break
            lowered = executable.name.casefold()
            if any(token in lowered for token in ignored) or executable.is_symlink():
                continue
            architecture = pe_architecture(executable)
            if not architecture:
                continue
            directory = executable.parent.resolve()
            if root != directory and root not in directory.parents:
                continue
            result.append({"exe": str(executable), "directory": str(directory), "architecture": architecture})
        return sorted(result, key=lambda item: item["exe"].casefold())

    def _target(self, appid: str, exe: str) -> tuple[dict[str, Any], dict[str, str]]:
        game = self._game(appid)
        target = next((item for item in self._targets(game) if item["exe"] == exe), None)
        if not target:
            raise ValueError("select an executable reported by this plugin")
        return game, target

    def _runtime(self, architecture: str) -> Path:
        root = self._root() / "runtime" / architecture
        required = [root / "reshade/dxgi.dll", root / "dlssnr-amd", root / "model-tools/extract_model.sh", root / "ini/dlssnr-amd-addon.ini"]
        if not all(path.exists() for path in required):
            raise ValueError("the plugin runtime is incomplete; install a release build, not a source checkout")
        return root

    def _validate_settings(self, settings: dict[str, Any]) -> dict[str, str]:
        if not isinstance(settings, dict) or set(settings) - EDITABLE:
            raise ValueError("unsupported NR setting")
        result: dict[str, str] = {}
        for key, raw in settings.items():
            value = str(raw).strip()
            if key in {"Enabled", "Sound"} and value not in {"0", "1"}:
                raise ValueError(f"{key} must be 0 or 1")
            if key == "Passes" and value not in {"1", "2"}:
                raise ValueError("Passes must be 1 or 2")
            if key == "Exposure" and value not in {"auto", "off", "fixed"}:
                raise ValueError("Exposure must be auto, off, or fixed")
            if key == "Curve" and value not in {"none", "neutral", "reinhard", "filmic", "gt", "aces", "agx"}:
                raise ValueError("unsupported curve")
            if key in {"ExposureBias", "Contrast", "Saturation", "WorkingScale"}:
                number = float(value)
                if not -100 <= number <= 100 or (key == "WorkingScale" and not .25 <= number <= 1):
                    raise ValueError(f"{key} is out of range")
            result[key] = value
        return result

    def _settings(self, directory: Path) -> dict[str, str]:
        path = directory / "dlssnr-amd.ini"
        if not path.is_file():
            return {}
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(path, encoding="utf-8")
        result: dict[str, str] = {}
        for section in ("DlssNr", "Preprocess"):
            if parser.has_section(section):
                result.update({key: value for key, value in parser.items(section) if key in EDITABLE})
        return result

    def _write_settings(self, directory: Path, settings: dict[str, Any]) -> dict[str, str]:
        path = directory / "dlssnr-amd.ini"
        if not path.is_file():
            raise ValueError("NR is not installed for this target")
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(path, encoding="utf-8")
        for key, value in self._validate_settings(settings).items():
            section = "DlssNr" if key in {"WorkingScale", "Passes"} else "Preprocess"
            if not parser.has_section(section):
                parser.add_section(section)
            parser.set(section, key, value)
        temporary = path.with_suffix(".ini.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            parser.write(output)
        temporary.replace(path)
        return self._settings(directory)

    def _extract_model(self, runtime: Path, supplied: str) -> Path:
        source = Path(supplied).expanduser().resolve()
        if source.name.casefold() != MODEL_NAME and source.suffix.casefold() != ".zip":
            raise ValueError("select nvngx_dlssnr.dll or a zip containing it")
        if not source.is_file():
            raise ValueError("the selected model source does not exist")
        scratch = Path(tempfile.mkdtemp(prefix="decky-dlssnr-"))
        output = scratch / "dlssnr.bin"
        try:
            completed = subprocess.run(["bash", str(runtime / "model-tools/extract_model.sh"), str(source), str(output)], text=True, capture_output=True, timeout=240, check=False)
            if completed.returncode or not output.is_file():
                raise ValueError("model extraction failed: " + (completed.stderr.strip() or completed.stdout.strip() or "unknown error"))
            return output
        except Exception:
            shutil.rmtree(scratch, ignore_errors=True)
            raise

    def _copy_assets(self, runtime: Path, directory: Path, model: Path, backup: Path | None) -> list[dict[str, str]]:
        sources = [(runtime / "reshade", directory), (runtime / "dlssnr-amd", directory / "dlssnr-amd")]
        entries: list[tuple[Path, Path]] = []
        for source_root, target_root in sources:
            for source in source_root.rglob("*"):
                if source.is_file() and source.name != "dlssnr.bin":
                    entries.append((source, target_root / source.relative_to(source_root)))
        entries += [(model, directory / "dlssnr-amd/dlssnr.bin"), (runtime / "ini/dlssnr-amd-addon.ini", directory / "dlssnr-amd.ini")]
        conflicts = [target for _, target in entries if target.exists()]
        if conflicts and backup is None:
            raise ValueError("target already contains NR/ReShade files; enable backup-and-replace or remove the old installation first")
        installed: list[dict[str, str]] = []
        replaced: list[tuple[Path, Path]] = []
        try:
            for source, target in entries:
                relative = str(target.relative_to(directory))
                if target.exists() and backup is not None:
                    saved = backup / relative
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, saved)
                    replaced.append((saved, target))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                installed.append({"path": relative, "sha256": sha256(target)})
            return installed
        except Exception:
            # A partial failed install must not strand an injected DXGI file. Restore
            # every backup first, then remove only files whose just-written hash proves
            # they still belong to this interrupted operation.
            for saved, target in reversed(replaced):
                if saved.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(saved, target)
            for entry in installed:
                target = directory / entry["path"]
                if target.is_file() and sha256(target) == entry["sha256"]:
                    target.unlink()
            raise

    async def list_games(self) -> dict[str, Any]:
        games = self._games()
        for game in games:
            game["targets"] = self._targets(game)
            game["installed"] = self._read_manifest(game["appid"]) is not None
        return {"games": games}

    async def install(self, appid: str, exe: str, model_path: str, backup_replace: bool, anti_cheat_acknowledged: bool) -> dict[str, Any]:
        if not anti_cheat_acknowledged:
            raise ValueError("installation is blocked until you confirm this is an offline game with no anti-cheat")
        if self._read_manifest(appid):
            raise ValueError("this game is already managed; remove it first or change settings")
        game, target = self._target(appid, exe)
        runtime = self._runtime(target["architecture"])
        directory = Path(target["directory"])
        backup = None
        if backup_replace:
            backup = self._data() / "backups" / appid / str(int(time.time()))
            backup.mkdir(parents=True, exist_ok=False)
        model = self._extract_model(runtime, model_path)
        try:
            files = self._copy_assets(runtime, directory, model, backup)
        finally:
            shutil.rmtree(model.parent, ignore_errors=True)
        manifest = {"format": MANIFEST_VERSION, "appid": appid, "name": game["name"], "directory": str(directory), "exe": target["exe"], "architecture": target["architecture"], "files": files, "backup": str(backup) if backup else None}
        self._manifest_path(appid).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return {"message": "Installed. Add the shown launch option, then restart the game.", "launch_option": 'WINEDLLOVERRIDES="dxgi=n,b" %command%', "manifest": manifest, "settings": self._settings(directory)}

    async def remove(self, appid: str) -> dict[str, Any]:
        manifest = self._read_manifest(appid)
        if not manifest:
            raise ValueError("no managed installation exists for this game")
        directory = Path(manifest["directory"])
        removed, preserved, restored = [], [], []
        for entry in manifest.get("files", []):
            path = (directory / entry["path"]).resolve()
            if directory != path.parent and directory not in path.parents:
                continue
            if path.is_file() and sha256(path) == entry["sha256"]:
                path.unlink(); removed.append(entry["path"])
            elif path.exists():
                preserved.append(entry["path"])
        backup = Path(manifest["backup"]) if manifest.get("backup") else None
        if backup and backup.is_dir():
            for saved in backup.rglob("*"):
                if saved.is_file():
                    target = directory / saved.relative_to(backup)
                    if not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(saved, target); restored.append(str(saved.relative_to(backup)))
        for candidate in sorted(directory.rglob("*"), reverse=True):
            if candidate.is_dir():
                try: candidate.rmdir()
                except OSError: pass
        self._manifest_path(appid).unlink(missing_ok=True)
        return {"message": "Removed only files whose hashes matched this plugin's install record.", "removed": removed, "preserved": preserved, "restored": restored}

    async def get_status(self, appid: str) -> dict[str, Any]:
        manifest = self._read_manifest(appid)
        if not manifest:
            return {"installed": False}
        directory = Path(manifest["directory"])
        integrity = all((directory / entry["path"]).is_file() and sha256(directory / entry["path"]) == entry["sha256"] for entry in manifest["files"])
        return {"installed": True, "manifest": manifest, "integrity": integrity, "settings": self._settings(directory)}

    async def save_settings(self, appid: str, settings: dict[str, Any]) -> dict[str, Any]:
        manifest = self._read_manifest(appid)
        if not manifest:
            raise ValueError("install NR for this game first")
        return {"settings": self._write_settings(Path(manifest["directory"]), settings)}

