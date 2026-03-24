"""Prompts for the spec generator (buildable unit → tact spec)."""

SYSTEM = """\
You are a technical specification writer. Your job is to transform a validated project \
idea into a complete, tact-compatible project specification.

The specification must include:
1. Product definition: name, vision, goals with success criteria, tech stack, constraints
2. Architecture: patterns, invariants, conventions, key decisions
3. Requirements: broken into discrete, testable requirements with acceptance criteria

Write specifications that are:
- Precise enough for an AI agent to implement without ambiguity
- Scoped to an MVP that can be built in 1-3 focused sessions
- Structured so requirements can be worked on independently/in parallel
"""


def build_spec_prompt(unit_json: str, evaluation_json: str) -> str:
    return f"""\
Generate a complete tact-compatible project specification for this idea.

IDEA:
{unit_json}

EVALUATION:
{evaluation_json}

Generate:

1. PRODUCT:
   - name: kebab-case package name
   - version: "0.1.0"
   - vision: 1-2 sentence product vision
   - goals: 2-4 goals, each with id (G-1, G-2...), description, and measurable successCriteria
   - techStack: languages, frameworks, infrastructure
   - constraints: key technical/scope constraints for MVP

2. ARCHITECTURE:
   - patterns: architectural patterns with scope
   - invariants: rules that must never be violated
   - conventions: coding/naming conventions
   - decisions: 2-3 key architectural decisions with rationale

3. REQUIREMENTS (5-10):
   - title: imperative sentence
   - priority: critical | high | medium | low
   - description: what and why
   - acceptanceCriteria: 2-5 testable criteria per requirement
   - dependencies: which other requirements this depends on (by title)

Focus the requirements on MVP scope. Ensure acceptance criteria are specific and testable.\
"""
