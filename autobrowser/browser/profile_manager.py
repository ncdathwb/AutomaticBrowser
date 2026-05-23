"""Multi-profile manager – create, delete, and switch between Chrome profiles.

Each profile maps to a separate --user-data-dir so identities are isolated.
"""

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

PROFILES_FILENAME = "profiles.json"
ACTIVE_PROFILE_FILENAME = "active_profile.txt"


@dataclass
class Profile:
    id: str
    name: str
    chrome_profile_dir: str  # relative to data_dir
    created_at: str = ""


@dataclass
class ProfileStore:
    profiles: list[Profile] = field(default_factory=list)
    active_id: str = ""


def _store_path(data_dir: Path) -> Path:
    return data_dir / PROFILES_FILENAME


def _active_path(data_dir: Path) -> Path:
    return data_dir / ACTIVE_PROFILE_FILENAME


def load_store(data_dir: Path) -> ProfileStore:
    path = _store_path(data_dir)
    if not path.is_file():
        return ProfileStore()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        profiles = [
            Profile(
                id=p["id"],
                name=p["name"],
                chrome_profile_dir=p["chrome_profile_dir"],
                created_at=p.get("created_at", ""),
            )
            for p in raw.get("profiles", [])
        ]
    except (json.JSONDecodeError, OSError, KeyError):
        return ProfileStore()

    active_id = ""
    active_path = _active_path(data_dir)
    if active_path.is_file():
        try:
            active_id = active_path.read_text(encoding="utf-8").strip()
        except OSError:
            pass

    # Validate active_id still exists
    if active_id and not any(p.id == active_id for p in profiles):
        active_id = ""

    return ProfileStore(profiles=profiles, active_id=active_id)


def save_store(data_dir: Path, store: ProfileStore) -> bool:
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        _store_path(data_dir).write_text(
            json.dumps(
                {
                    "profiles": [
                        {
                            "id": p.id,
                            "name": p.name,
                            "chrome_profile_dir": p.chrome_profile_dir,
                            "created_at": p.created_at,
                        }
                        for p in store.profiles
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        _active_path(data_dir).write_text(store.active_id, encoding="utf-8")
        return True
    except OSError:
        return False


def create_profile(data_dir: Path, name: str, profile_id: str) -> Profile | None:
    """Create a new profile. Returns None if ID already exists."""
    store = load_store(data_dir)
    if any(p.id == profile_id for p in store.profiles):
        return None

    import datetime

    chrome_dir = f"chrome_profile_{profile_id}"
    profile = Profile(
        id=profile_id,
        name=name,
        chrome_profile_dir=chrome_dir,
        created_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    store.profiles.append(profile)
    if not store.active_id:
        store.active_id = profile_id

    if save_store(data_dir, store):
        return profile
    return None


def delete_profile(data_dir: Path, profile_id: str) -> bool:
    """Delete a profile and its Chrome data directory."""
    store = load_store(data_dir)
    target = next((p for p in store.profiles if p.id == profile_id), None)
    if not target:
        return False

    store.profiles = [p for p in store.profiles if p.id != profile_id]
    if store.active_id == profile_id:
        store.active_id = store.profiles[0].id if store.profiles else ""

    if not save_store(data_dir, store):
        return False

    chrome_dir = data_dir / target.chrome_profile_dir
    if chrome_dir.exists():
        try:
            shutil.rmtree(chrome_dir, ignore_errors=True)
        except OSError:
            pass
    return True


def set_active_profile(data_dir: Path, profile_id: str) -> bool:
    """Switch the active profile."""
    store = load_store(data_dir)
    if not any(p.id == profile_id for p in store.profiles):
        return False
    store.active_id = profile_id
    return save_store(data_dir, store)


def get_active_profile_dir(data_dir: Path) -> Path:
    """Return the Chrome user-data-dir for the active profile."""
    store = load_store(data_dir)
    active = next((p for p in store.profiles if p.id == store.active_id), None)
    if active:
        return data_dir / active.chrome_profile_dir
    # Fallback: default profile dir
    return data_dir / "chrome_profile"
