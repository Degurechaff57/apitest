import hashlib
import json
from pathlib import Path

from apitest.models.example import TestExample


def _cache_key(spec_path: str, coverage: str, area_names: list[str]) -> str:
    """Build a deterministic cache key from input parameters."""
    payload = json.dumps({
        "spec": Path(spec_path).resolve().as_posix(),
        "coverage": coverage,
        "areas": sorted(area_names),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _cache_dir(spec_path: str) -> Path:
    """Resolve cache directory next to the spec file or in CWD."""
    spec = Path(spec_path)
    if spec.exists():
        return spec.parent / ".apitest_cache"
    return Path.cwd() / ".apitest_cache"


def get_cached_examples(spec_path: str, coverage: str,
                        area_names: list[str]) -> list[TestExample] | None:
    """Return cached examples if they exist for these inputs, otherwise None."""
    cache_path = _cache_dir(spec_path) / f"{_cache_key(spec_path, coverage, area_names)}.json"
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text())
        return [TestExample.from_dict(e) for e in data.get("examples", [])]
    except (json.JSONDecodeError, KeyError):
        return None


def put_cached_examples(spec_path: str, coverage: str, area_names: list[str],
                        examples: list[TestExample]) -> None:
    """Store examples in the cache."""
    cache_path = _cache_dir(spec_path) / f"{_cache_key(spec_path, coverage, area_names)}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"examples": [e.to_dict() for e in examples]}
    cache_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def clear_cache(spec_path: str) -> int:
    """Remove all cache entries for a spec. Returns count of removed files."""
    cache_dir = _cache_dir(spec_path)
    if not cache_dir.exists():
        return 0
    count = 0
    for f in cache_dir.glob("*.json"):
        f.unlink()
        count += 1
    return count
