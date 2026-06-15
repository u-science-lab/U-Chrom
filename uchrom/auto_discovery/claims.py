"""Claim refresh helpers for iterative auto-discovery."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


CLAIM_KNOWLEDGE_MODES = {"off", "knowledge_guided", "browser_refresh"}


@dataclass
class ClaimRefreshResult:
    """Summary of one claim-refresh pass."""

    mode: str
    claims_path: str | None
    retrieval_log_path: str
    n_claims: int
    source_paths: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def refresh_literature_claims_for_iteration(
    *,
    run_dir: str | Path,
    schema: Mapping[str, Any],
    seed_claim_paths: Sequence[str | Path] | None = None,
    mode: str = "knowledge_guided",
) -> ClaimRefreshResult:
    """Materialize per-iteration literature/user claims.

    ``knowledge_guided`` keeps the run closed to network access and only
    normalizes existing source-backed claim caches plus h5cd references and
    user annotations.  ``browser_refresh`` currently records that a network
    refresh was requested, then falls back to the same cached behavior; this
    keeps the iterative orchestrator ready for a real browser worker without
    silently inventing literature claims.
    """
    mode = str(mode or "knowledge_guided")
    if mode not in CLAIM_KNOWLEDGE_MODES:
        raise ValueError(
            "knowledge_mode must be one of "
            + ", ".join(sorted(CLAIM_KNOWLEDGE_MODES))
        )

    run_dir = Path(run_dir)
    literature_dir = run_dir / "literature"
    literature_dir.mkdir(parents=True, exist_ok=True)
    claims_path = literature_dir / "claims.jsonl"
    retrieval_log_path = literature_dir / "retrieval_log.jsonl"

    rows: list[dict[str, Any]] = []
    source_paths: list[str] = []
    notes: list[str] = []
    log_rows: list[dict[str, Any]] = [{
        "event": "claim_refresh_started",
        "mode": mode,
    }]

    if mode == "off":
        notes.append("knowledge refresh disabled")
        _write_jsonl(retrieval_log_path, log_rows + [{
            "event": "claim_refresh_skipped",
            "reason": "knowledge_mode=off",
        }])
        return ClaimRefreshResult(
            mode=mode,
            claims_path=None,
            retrieval_log_path=str(retrieval_log_path),
            n_claims=0,
            source_paths=[],
            notes=notes,
        )

    if mode == "browser_refresh":
        notes.append(
            "browser_refresh requested but no browser worker is configured; "
            "using cached claims, references, and annotations only"
        )

    for raw_path in seed_claim_paths or []:
        path = Path(raw_path)
        if not path.exists():
            log_rows.append({
                "event": "seed_claim_path_missing",
                "path": str(path),
            })
            continue
        source_paths.append(str(path))
        seed_rows = [
            _normalize_claim_row(row, default_extraction_method="cached_claims")
            for row in _read_jsonl(path)
            if isinstance(row, Mapping)
        ]
        rows.extend(seed_rows)
        log_rows.append({
            "event": "seed_claim_path_loaded",
            "path": str(path),
            "n_claims": len(seed_rows),
        })

    schema_rows = _claims_from_schema_knowledge(schema)
    rows.extend(schema_rows)
    if schema_rows:
        log_rows.append({
            "event": "schema_knowledge_loaded",
            "n_claims": len(schema_rows),
        })

    rows = _dedupe_claim_rows(rows)
    rows = _scope_claim_rows_to_run(rows, run_dir)
    rows = _link_claim_rows_to_run_ideas(rows, run_dir)
    if rows:
        log_rows.append({
            "event": "literature_queries_materialized",
            "n_queries": len(rows),
            "queries": [row.get("search_query") for row in rows[:20]],
        })
    if rows:
        _write_jsonl(claims_path, rows)
    elif claims_path.exists():
        claims_path.unlink()
    _write_jsonl(retrieval_log_path, log_rows + [{
        "event": "claim_refresh_completed",
        "n_claims": len(rows),
        "notes": notes,
    }])

    return ClaimRefreshResult(
        mode=mode,
        claims_path=str(claims_path) if rows else None,
        retrieval_log_path=str(retrieval_log_path),
        n_claims=len(rows),
        source_paths=source_paths,
        notes=notes,
    )


def _claims_from_schema_knowledge(schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ref in schema.get("references") or []:
        if not isinstance(ref, Mapping):
            continue
        notes = str(ref.get("notes") or "").strip()
        title = str(ref.get("title") or ref.get("doi") or ref.get("url") or "").strip()
        if not notes and not title:
            continue
        reference_id = str(ref.get("reference_id") or ref.get("doi") or ref.get("url") or title)
        claim_text = notes or f"Dataset reference available: {title}."
        rows.append(_normalize_claim_row({
            "claim_id": f"schema_reference_{_slug(reference_id)}",
            "claim": claim_text,
            "summary": notes or title,
            "reference_id": reference_id,
            "source_title": title or reference_id,
            "url": ref.get("url"),
            "doi": ref.get("doi"),
            "pmid": ref.get("pmid"),
            "year": ref.get("year"),
            "modalities": _modalities_from_schema(schema),
            "extraction_method": "h5cd_reference",
            "raw_reference": dict(ref),
        }))

    for ann in schema.get("user_annotations") or []:
        if not isinstance(ann, Mapping):
            continue
        text = str(ann.get("text") or "").strip()
        if not text:
            continue
        annotation_id = str(ann.get("annotation_id") or _slug(text[:80]))
        rows.append(_normalize_claim_row({
            "claim_id": f"user_annotation_{_slug(annotation_id)}",
            "claim": text,
            "summary": text,
            "reference_id": annotation_id,
            "source_title": f"User annotation: {ann.get('scope') or annotation_id}",
            "modalities": _modalities_from_schema(schema),
            "extraction_method": "h5cd_user_annotation",
            "raw_annotation": dict(ann),
        }))
    return rows


def _normalize_claim_row(
    row: Mapping[str, Any],
    *,
    default_extraction_method: str | None = None,
) -> dict[str, Any]:
    source = row.get("source") if isinstance(row.get("source"), Mapping) else {}
    entities = row.get("entities") if isinstance(row.get("entities"), Mapping) else {}
    claim = (
        row.get("claim")
        or row.get("claim_text")
        or row.get("text")
        or row.get("summary")
    )
    normalized = dict(row)
    if claim is not None:
        normalized["claim"] = str(claim)
    normalized.setdefault("claim_id", _stable_claim_id(normalized))
    normalized.setdefault(
        "reference_id",
        source.get("reference_id")
        or row.get("doi")
        or source.get("doi")
        or row.get("pmid")
        or source.get("pmid")
        or row.get("url")
        or source.get("url")
        or f"reference_for_{normalized['claim_id']}",
    )
    normalized.setdefault("source_title", source.get("title") or row.get("title"))
    normalized.setdefault("url", source.get("url"))
    normalized.setdefault("doi", source.get("doi"))
    normalized.setdefault("pmid", source.get("pmid"))
    normalized.setdefault("year", source.get("year"))
    for key in ("genes", "cell_types", "markers", "modalities"):
        if key not in normalized and key in entities:
            normalized[key] = entities[key]
    if default_extraction_method is not None:
        normalized.setdefault("extraction_method", default_extraction_method)
    return normalized


def _dedupe_claim_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        normalized = _normalize_claim_row(row)
        claim_id = str(normalized.get("claim_id"))
        existing = unique.get(claim_id)
        if existing is None:
            unique[claim_id] = normalized
        else:
            existing.update({k: v for k, v in normalized.items() if v not in (None, "", [])})
    return list(unique.values())


def _scope_claim_rows_to_run(
    rows: Sequence[Mapping[str, Any]],
    run_dir: Path,
) -> list[dict[str, Any]]:
    scoped: list[dict[str, Any]] = []
    scope = run_dir.name or "run"
    for row in rows:
        next_row = dict(row)
        base_claim_id = str(next_row.get("claim_id") or _stable_claim_id(next_row))
        next_row["source_claim_id"] = base_claim_id
        next_row["claim_id"] = f"{scope}_{base_claim_id}"
        next_row["search_iteration"] = scope
        next_row.setdefault(
            "search_query",
            _claim_search_query(next_row),
        )
        scoped.append(next_row)
    return scoped


def _link_claim_rows_to_run_ideas(
    rows: Sequence[Mapping[str, Any]],
    run_dir: Path,
) -> list[dict[str, Any]]:
    idea_rows = [
        row for row in _read_jsonl_if_exists(run_dir / "ideas.jsonl")
        if isinstance(row, Mapping) and row.get("idea_id")
    ]
    if not idea_rows:
        return [dict(row) for row in rows]
    idea_tokens = [
        (str(row.get("idea_id")), _idea_entity_tokens(row))
        for row in idea_rows
    ]
    linked_rows: list[dict[str, Any]] = []
    for row in rows:
        next_row = dict(row)
        tokens = _claim_entity_tokens(next_row)
        related = set(_as_str_list(next_row.get("related_idea_ids")))
        if tokens:
            for idea_id, idea_token_set in idea_tokens:
                score = _claim_idea_overlap_score(tokens, idea_token_set)
                if score >= 2:
                    related.add(idea_id)
        if related:
            next_row["related_idea_ids"] = sorted(related)
        linked_rows.append(next_row)
    return linked_rows


def _modalities_from_schema(schema: Mapping[str, Any]) -> list[str]:
    modalities = schema.get("modalities") or {}
    if not isinstance(modalities, Mapping):
        return []
    return [
        str(key)
        for key, value in modalities.items()
        if isinstance(value, Mapping) and value.get("present")
    ]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return _read_jsonl(path)


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str, sort_keys=True) + "\n")


def _stable_claim_id(row: Mapping[str, Any]) -> str:
    text = str(
        row.get("claim")
        or row.get("claim_text")
        or row.get("summary")
        or row.get("text")
        or "claim"
    )
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "claim"
    payload = json.dumps(row, sort_keys=True, default=str)
    import hashlib

    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
    return f"{slug}-{digest}"


def _claim_search_query(row: Mapping[str, Any]) -> str:
    terms = [
        *_as_str_list(row.get("cell_types")),
        *_as_str_list(row.get("genes")),
        *_as_str_list(row.get("markers")),
    ]
    title = str(row.get("source_title") or row.get("title") or "").strip()
    if title:
        terms.append(title)
    if not terms:
        terms.append(str(row.get("claim") or row.get("summary") or "literature claim")[:120])
    return " ".join(_unique_strings(terms))


def _claim_entity_tokens(row: Mapping[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for key in ("genes", "markers", "cell_types"):
        tokens.update(_tokenize_values(_as_str_list(row.get(key))))
    return tokens


def _idea_entity_tokens(row: Mapping[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for key in ("cell_types", "modalities", "required_fields"):
        tokens.update(_tokenize_values(_as_str_list(row.get(key))))
    text_fields = [
        row.get("idea_title"),
        row.get("biological_hypothesis"),
        row.get("computable_parameter"),
        row.get("analysis_plan"),
    ]
    tokens.update(_tokenize_values([str(value) for value in text_fields if value]))
    return tokens


def _claim_idea_overlap_score(claim_tokens: set[str], idea_tokens: set[str]) -> int:
    return len(claim_tokens & idea_tokens)


def _tokenize_values(values: Sequence[str]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        text = str(value)
        compact = _slug(text).replace("-", "")
        if compact:
            tokens.add(compact)
        for piece in re.split(r"[^A-Za-z0-9_.+-]+", text):
            piece = piece.strip().lower()
            if len(piece) >= 3:
                tokens.add(piece)
    return tokens


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _unique_strings(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        unique.append(text)
        seen.add(text)
    return unique


def _slug(value: Any) -> str:
    text = str(value).strip().lower()
    slug = re.sub(r"[^a-z0-9_.+-]+", "-", text).strip("-")
    return slug or "unknown"
