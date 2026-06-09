"""Evidence summaries for auto-discovery notebooks and reports."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from .ideas import DiscoveryIdea


@dataclass(frozen=True)
class EvidenceConclusion:
    """Human-readable evidence classification for one explored idea."""

    notebook_status: str
    hypothesis_status: str
    direction_status: str
    p_value: float | None
    effect_size: float | None
    summary: str


def classify_hypothesis_evidence(
    idea: DiscoveryIdea | Mapping[str, Any],
    verification: Mapping[str, Any] | None,
    *,
    alpha: float = 0.05,
) -> EvidenceConclusion:
    """Classify whether a verified notebook supports the biological hypothesis.

    ``verification.status == "pass"`` means U-Chrom could rerun the notebook and
    validate required fields, finite outputs, and an explicit statistical test.
    This function separately classifies the hypothesis evidence from p-value and
    effect direction so "verified" is not confused with "biologically true".
    """
    if not isinstance(idea, DiscoveryIdea):
        idea = DiscoveryIdea.from_dict(idea)
    verification = dict(verification or {})
    notebook_status = (
        "Notebook verified"
        if verification.get("status") == "pass"
        else f"Notebook {verification.get('status', 'not verified')}"
    )
    p_value = _finite_float_or_none(verification.get("p_value"))
    effect_size = _finite_float_or_none(
        verification.get("effect_size", verification.get("parameter_value"))
    )
    hypothesis_test_status = verification.get("hypothesis_test_status")
    if hypothesis_test_status == "insufficient_data":
        return EvidenceConclusion(
            notebook_status=notebook_status,
            hypothesis_status="Inconclusive",
            direction_status="Insufficient data",
            p_value=p_value,
            effect_size=effect_size,
            summary=(
                "The notebook ran, but the selected subset was too small or too "
                "degenerate for the requested statistical claim."
            ),
        )
    expected_sign = _expected_direction_sign(idea.expected_direction)
    observed_sign = _sign(effect_size)
    direction_status = _direction_status(expected_sign, observed_sign)

    if p_value is None:
        return EvidenceConclusion(
            notebook_status=notebook_status,
            hypothesis_status="Inconclusive",
            direction_status=direction_status,
            p_value=None,
            effect_size=effect_size,
            summary=(
                "The notebook did not expose a finite p-value, so the idea "
                "cannot be interpreted as statistical support."
            ),
        )

    significant = p_value <= alpha
    if direction_status == "Opposite direction" and significant:
        hypothesis_status = "Contradicted"
        summary = (
            "The hypothesis test is significant, but the observed effect is in "
            "the opposite direction from the idea."
        )
    elif direction_status == "Opposite direction":
        hypothesis_status = "Not supported"
        summary = (
            "The observed effect points opposite to the expected direction and "
            "does not provide statistical support in this subset."
        )
    elif significant:
        hypothesis_status = "Supported"
        summary = (
            "The observed effect is consistent with the expected direction and "
            "passes the nominal p <= 0.05 threshold."
        )
    elif p_value <= 0.10:
        hypothesis_status = "Borderline"
        summary = (
            "The observed effect is compatible with the expected direction, but "
            "does not pass the nominal p <= 0.05 threshold."
        )
    else:
        hypothesis_status = "Not supported"
        summary = (
            "The statistical test does not support the idea in this linked "
            "Takei subset under the notebook's operational definition."
        )
    return EvidenceConclusion(
        notebook_status=notebook_status,
        hypothesis_status=hypothesis_status,
        direction_status=direction_status,
        p_value=p_value,
        effect_size=effect_size,
        summary=summary,
    )


def structured_conclusion_markdown(
    idea: DiscoveryIdea | Mapping[str, Any],
    verification: Mapping[str, Any] | None,
) -> str:
    """Build the standard final interpretation Markdown for a notebook."""
    if not isinstance(idea, DiscoveryIdea):
        idea = DiscoveryIdea.from_dict(idea)
    verification = dict(verification or {})
    conclusion = classify_hypothesis_evidence(idea, verification)
    test_method = verification.get("test_method", "not reported")
    parameter_value = _format_number(verification.get("parameter_value"))
    p_value = _format_p(conclusion.p_value)
    effect = _format_number(conclusion.effect_size)
    observed = _format_number(verification.get("observed_statistic"))
    if observed == "not reported":
        observed = parameter_value
    checks = verification.get("checks") or {}
    passed_checks = ", ".join(sorted(k for k, v in checks.items() if v == "pass"))
    if not passed_checks:
        passed_checks = "not reported"
    notes = verification.get("notes") or []
    caveat = str(notes[0]) if notes else (
        "Interpret this as an exploratory result for the linked Takei subset, "
        "not as a population-level biological proof."
    )
    modalities = ", ".join(idea.modalities) or "not specified"
    cell_types = ", ".join(idea.cell_types) or "not specified"
    required = ", ".join(idea.required_fields[:8])
    if len(idea.required_fields) > 8:
        required += ", ..."
    return "\n".join([
        "## Final interpretation",
        "",
        f"**Hypothesis.** {idea.biological_hypothesis}",
        "",
        (
            f"**Exploration.** The notebook operationalized the idea as "
            f"`{idea.computable_parameter}` using modalities `{modalities}` in "
            f"cell type(s) `{cell_types}`. Required data fields checked: "
            f"`{required}`."
        ),
        "",
        (
            f"**Statistical evidence.** U-Chrom runner status: "
            f"**{conclusion.notebook_status}**. Test: {test_method}. "
            f"Observed statistic: {observed}; effect size: {effect}; "
            f"parameter value: {parameter_value}; p-value: {p_value}."
        ),
        "",
        (
            f"**Conclusion.** **{conclusion.hypothesis_status}** "
            f"({conclusion.direction_status}). {conclusion.summary}"
        ),
        "",
        (
            "**What verification means.** `Notebook verified` means the run "
            "passed schema/data checks, produced finite numeric output, and "
            "included an explicit p-value/effect-size hypothesis test. It does "
            "not mean the biological hypothesis is automatically correct."
        ),
        "",
        f"**Checks passed.** {passed_checks}.",
        "",
        f"**Main caveat.** {caveat}",
        "",
    ])


def _expected_direction_sign(text: str) -> int | None:
    lower = str(text).lower()
    if "positive" in lower:
        return 1
    if "negative" in lower:
        return -1
    positive_tokens = [
        "larger",
        "higher",
        "greater",
        "increase",
        "enrich",
        "stronger",
        "more",
        "exceed",
    ]
    negative_tokens = [
        "smaller",
        "lower",
        "less",
        "decrease",
        "reduced",
        "closer",
        "compact",
    ]
    if any(token in lower for token in positive_tokens):
        return 1
    if any(token in lower for token in negative_tokens):
        return -1
    return None


def _direction_status(expected_sign: int | None, observed_sign: int | None) -> str:
    if expected_sign is None or observed_sign is None:
        return "Direction not classified"
    if observed_sign == 0:
        return "Near zero effect"
    if expected_sign == observed_sign:
        return "Expected direction"
    return "Opposite direction"


def _finite_float_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _sign(value: float | None) -> int | None:
    if value is None:
        return None
    if abs(value) < 1e-12:
        return 0
    return 1 if value > 0 else -1


def _format_p(value: float | None) -> str:
    if value is None:
        return "not reported"
    if value < 1e-4:
        return f"{value:.2e}"
    return f"{value:.4g}"


def _format_number(value: Any) -> str:
    out = _finite_float_or_none(value)
    if out is None:
        return "not reported"
    if abs(out) >= 100 or (abs(out) < 1e-3 and out != 0):
        return f"{out:.3e}"
    return f"{out:.4g}"
