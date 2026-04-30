"""Persona-specific customer discovery interview guides for buildable ideas."""

from __future__ import annotations

import re
from typing import Any

from max.types.buildable_unit import BuildableUnit

SCHEMA_VERSION = "max.persona_interview_guide.v1"

SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("problem_severity", "Problem Severity"),
    ("current_workaround", "Current Workaround"),
    ("buying_process", "Buying Process"),
    ("risk_compliance", "Risk/Compliance"),
    ("validation_next_steps", "Validation Next Steps"),
)

_GENERIC_TARGET_USERS = {"", "both", "human", "humans", "agent", "agents", "user", "users"}
_SPLIT_RE = re.compile(r"\s*(?:,|/|\||\band\b|\bor\b)\s*", re.IGNORECASE)


def generate_persona_interview_guide(
    unit: BuildableUnit,
    evidence_chain: dict[str, Any] | None = None,
    *,
    profile_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic customer-discovery guide from one idea and evidence chain."""
    chain = evidence_chain or {}
    profile = profile_context or {}
    evidence_references = _evidence_references(unit, chain)
    personas = [
        _persona(name, unit, evidence_references=evidence_references)
        for name in _infer_personas(unit, chain, profile)
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.persona_interview_guide",
        "idea_id": unit.id,
        "title": unit.title,
        "source": {
            "domain": _clean(unit.domain),
            "category": str(unit.category),
            "target_users": _clean(unit.target_users),
            "specific_user": _clean(unit.specific_user),
            "buyer": _clean(unit.buyer),
            "profile_context_available": bool(profile),
            "evidence_signal_count": len(evidence_references),
        },
        "personas": personas,
        "evidence_references": evidence_references,
    }


def render_persona_interview_guide_markdown(guide: dict[str, Any]) -> str:
    """Render a generated persona interview guide as deterministic markdown."""
    source = guide.get("source", {})
    lines = [
        f"# Persona Interview Guide: {_text(guide.get('title'))}",
        "",
        f"- Schema version: {_text(guide.get('schema_version'))}",
        f"- Idea ID: {_text(guide.get('idea_id'))}",
        f"- Domain: {_text(source.get('domain'))}",
        f"- Category: {_text(source.get('category'))}",
        f"- Target users: {_text(source.get('target_users'))}",
        "",
        "## Personas",
        "",
    ]

    personas = guide.get("personas") or []
    if not personas:
        lines.append("No personas were inferred.")
    for persona in personas:
        lines.extend(
            [
                f"### {_text(persona.get('name'))}",
                "",
                f"- Role type: {_text(persona.get('role_type'))}",
                f"- Interview goal: {_text(persona.get('interview_goal'))}",
                "",
            ]
        )
        sections = persona.get("sections") or {}
        for section_key, section_title in SECTION_ORDER:
            section = sections.get(section_key, {})
            lines.extend([f"#### {section_title}", ""])
            for question in section.get("questions") or []:
                lines.append(f"- {question}")
            lines.append("")

    lines.extend(["## Evidence References", ""])
    references = guide.get("evidence_references") or []
    if references:
        for reference in references:
            title = _text(reference.get("title")) or "Untitled evidence"
            url = _text(reference.get("url")) or "no-url"
            ref_id = _text(reference.get("id")) or "unknown"
            source_type = _text(reference.get("source_type")) or "signal"
            lines.append(f"- {source_type}:{ref_id} - {title} - {url}")
    else:
        lines.append("No evidence references were provided.")

    return "\n".join(lines).rstrip() + "\n"


def _infer_personas(
    unit: BuildableUnit,
    evidence_chain: dict[str, Any],
    profile_context: dict[str, Any],
) -> list[str]:
    candidates: list[str] = []
    candidates.extend(_split_people(unit.specific_user))
    candidates.extend(_split_people(unit.target_users))
    candidates.extend(_split_people(unit.buyer))

    for key in ("personas", "target_users", "allowed_target_users", "specific_users", "buyers"):
        candidates.extend(_context_people(profile_context.get(key)))

    idea = evidence_chain.get("idea")
    if isinstance(idea, dict):
        candidates.extend(_split_people(idea.get("specific_user")))
        candidates.extend(_split_people(idea.get("target_users")))
        candidates.extend(_split_people(idea.get("buyer")))

    for signal in evidence_chain.get("signals") or []:
        if not isinstance(signal, dict):
            continue
        metadata = signal.get("metadata") if isinstance(signal.get("metadata"), dict) else {}
        for key in ("persona", "personas", "target_user", "target_users", "user_role", "buyer"):
            candidates.extend(_context_people(metadata.get(key)))
        candidates.extend(_tag_personas(signal.get("tags")))

    personas = _dedupe(
        _normalize_persona(candidate)
        for candidate in candidates
        if _normalize_persona(candidate).lower() not in _GENERIC_TARGET_USERS
    )
    if personas:
        return personas

    domain = _clean(unit.domain) or _clean(profile_context.get("domain")) or "product"
    return [f"{domain.replace('-', ' ').title()} Practitioner"]


def _persona(
    name: str,
    unit: BuildableUnit,
    *,
    evidence_references: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence_titles = [reference["title"] for reference in evidence_references[:2] if reference["title"]]
    return {
        "name": name,
        "role_type": _role_type(name, unit),
        "interview_goal": f"Validate whether {name} urgently needs {unit.title}.",
        "sections": {
            "problem_severity": _section(
                "problem_severity",
                [
                    f"How often do you encounter this problem: {unit.problem}?",
                    "What happens if this problem is not solved during a normal work cycle?",
                    "Which recent incident, delay, or missed outcome best shows the severity?",
                ],
            ),
            "current_workaround": _section(
                "current_workaround",
                [
                    f"What do you use today instead of {unit.title}?",
                    f"How well does this workaround hold up: {_fallback(unit.current_workaround, 'the current process')}?",
                    "Where does the workaround create manual effort, rework, or handoff risk?",
                ],
            ),
            "buying_process": _section(
                "buying_process",
                [
                    f"Who besides {name} would approve, block, or fund a solution like this?",
                    f"What evidence would {_fallback(unit.buyer, 'the buyer')} need before starting a pilot?",
                    "What budget, procurement, or integration steps would slow adoption?",
                ],
            ),
            "risk_compliance": _section(
                "risk_compliance",
                [
                    "What security, privacy, compliance, or operational risks would this need to clear?",
                    f"Which risk is most concerning: {_risk_prompt(unit)}?",
                    "What data, access, or audit constraints would shape the first version?",
                ],
            ),
            "validation_next_steps": _section(
                "validation_next_steps",
                [
                    f"Would you participate in this validation plan: {_fallback(unit.validation_plan, 'a focused customer-discovery follow-up')}?",
                    f"What would prove the value proposition is real: {_fallback(unit.value_proposition, 'the promised outcome')}?",
                    _evidence_question(evidence_titles),
                ],
            ),
        },
    }


def _section(section_id: str, questions: list[str]) -> dict[str, Any]:
    return {"id": section_id, "questions": questions}


def _evidence_references(unit: BuildableUnit, evidence_chain: dict[str, Any]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for signal in evidence_chain.get("signals") or []:
        if not isinstance(signal, dict):
            continue
        signal_id = _clean(signal.get("id"))
        if not signal_id:
            continue
        references.append(
            {
                "id": signal_id,
                "source_type": _clean(signal.get("source_type")) or "signal",
                "title": _clean(signal.get("title")) or signal_id,
                "url": _clean(signal.get("url")),
                "signal_role": _clean(signal.get("signal_role")),
            }
        )

    known_ids = {reference["id"] for reference in references}
    for signal_id in unit.evidence_signals:
        clean_id = _clean(signal_id)
        if clean_id and clean_id not in known_ids:
            references.append(
                {
                    "id": clean_id,
                    "source_type": "signal",
                    "title": clean_id,
                    "url": "",
                    "signal_role": "",
                }
            )
    return references


def _role_type(name: str, unit: BuildableUnit) -> str:
    normalized = name.lower()
    if _clean(unit.buyer).lower() == normalized or any(
        term in normalized for term in ("buyer", "lead", "director", "vp", "head")
    ):
        return "buyer"
    if any(term in normalized for term in ("security", "compliance", "legal", "risk")):
        return "risk reviewer"
    return "user"


def _risk_prompt(unit: BuildableUnit) -> str:
    return "; ".join(_clean(risk) for risk in unit.domain_risks if _clean(risk)) or (
        "adoption, trust, data access, or workflow disruption"
    )


def _evidence_question(evidence_titles: list[str]) -> str:
    if evidence_titles:
        return f"Which evidence should we verify next: {'; '.join(evidence_titles)}?"
    return "What proof should we collect next before deciding whether to build?"


def _context_people(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _split_people(value)
    if isinstance(value, dict):
        for key in ("name", "role", "title", "persona"):
            if _clean(value.get(key)):
                return [_clean(value.get(key))]
        return []
    if isinstance(value, (list, tuple, set)):
        people: list[str] = []
        for item in value:
            people.extend(_context_people(item))
        return people
    return _split_people(value)


def _split_people(value: Any) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    return [_clean(part) for part in _SPLIT_RE.split(text) if _clean(part)]


def _tag_personas(value: Any) -> list[str]:
    tags = value if isinstance(value, list) else []
    personas: list[str] = []
    for tag in tags:
        text = _clean(tag)
        if text.startswith("persona:"):
            personas.append(text.split(":", 1)[1])
        elif text.startswith("role:"):
            personas.append(text.split(":", 1)[1])
    return personas


def _normalize_persona(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    return text.replace("_", " ").replace("-", " ").title()


def _fallback(value: Any, fallback: str) -> str:
    return _clean(value) or fallback


def _text(value: Any) -> str:
    text = _clean(value)
    return text if text else "none"


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _dedupe(values: list[str] | Any) -> list[str]:
    return [value for value in dict.fromkeys(_clean(value) for value in values) if value]
