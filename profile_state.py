import json
from pathlib import Path

import psutil


LOCK_FILES = (
    "lockfile",
    "SingletonCookie",
    "SingletonLock",
    "SingletonSocket",
    "DevToolsActivePort",
)


def prepare_profile(profile_dir: Path) -> int:
    profile_dir.mkdir(parents=True, exist_ok=True)
    closed_count = close_profile_processes(profile_dir) if has_lock_files(profile_dir) else 0
    remove_stale_locks(profile_dir)
    mark_profile_clean(profile_dir)
    return closed_count


def has_lock_files(profile_dir: Path) -> bool:
    return any((profile_dir / name).exists() for name in LOCK_FILES)


def close_profile_processes(profile_dir: Path, timeout: float = 5.0) -> int:
    profile_text = normalize_path(profile_dir.resolve())
    matches = []

    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = process.info.get("name") or ""
            cmdline = process.info.get("cmdline") or []
            if "chrome" not in name.lower():
                continue
            if profile_text not in normalize_text(" ".join(cmdline)):
                continue
            matches.append(process)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

    for process in matches:
        try:
            process.terminate()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass

    _, alive = psutil.wait_procs(matches, timeout=timeout)
    for process in alive:
        try:
            process.kill()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass

    return len(matches)


def remove_stale_locks(profile_dir: Path) -> None:
    for name in LOCK_FILES:
        path = profile_dir / name
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass


def mark_profile_clean(profile_dir: Path) -> None:
    patch_json_profile_state(profile_dir / "Local State")
    patch_json_profile_state(profile_dir / "Default" / "Preferences")


def patch_json_profile_state(path: Path) -> None:
    if not path.exists():
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    changed = False

    profile = data.setdefault("profile", {})
    if profile.get("exit_type") != "Normal":
        profile["exit_type"] = "Normal"
        changed = True
    if profile.get("exited_cleanly") is not True:
        profile["exited_cleanly"] = True
        changed = True

    session = data.setdefault("session", {})
    if session.get("restore_on_startup") == 1:
        session["restore_on_startup"] = 5
        changed = True

    if not changed:
        return

    try:
        path.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
    except OSError:
        pass


def normalize_path(path: Path) -> str:
    return normalize_text(str(path))


def normalize_text(text: str) -> str:
    return text.lower().replace("/", "\\")
