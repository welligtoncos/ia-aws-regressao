"""Utilitários genéricos para comparação e validação (regressão, QA, reconciliação)."""

from typing import Any, Dict, Iterable, List


def compare_records(expected: Dict[str, Any], actual: Dict[str, Any], keys: Iterable[str]) -> List[str]:
    """Compara campos entre dois registros e retorna lista de divergências."""
    diffs = []
    for key in keys:
        exp = expected.get(key)
        act = actual.get(key)
        if exp != act:
            diffs.append(f"{key}: expected={exp!r} actual={act!r}")
    return diffs


def summarize_diffs(diffs: List[str], max_items: int = 20) -> Dict[str, Any]:
    """Resume divergências para persistência ou log."""
    return {
        "passed": len(diffs) == 0,
        "diff_count": len(diffs),
        "diffs": diffs[:max_items],
        "truncated": len(diffs) > max_items,
    }
