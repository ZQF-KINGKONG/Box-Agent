"""Expert and expert-team session metadata for host integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_MAX_TEXT = 2000
_MAX_ITEMS = 12
_EXPERT_TEAM_EXECUTION_MODES = {"advisory", "orchestrated", "review_panel"}


def _clean_text(value: Any, *, max_len: int = _MAX_TEXT) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\r", "\n").split())[:max_len]


def _clean_block(value: Any, *, max_len: int = _MAX_TEXT) -> str:
    if not isinstance(value, str):
        return ""
    lines = [line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()[:max_len]


def _clean_list(value: Any, *, max_items: int = _MAX_ITEMS, max_len: int = 320) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = _clean_text(item, max_len=max_len)
        if text:
            items.append(text)
        if len(items) >= max_items:
            break
    return items


def _clean_execution_mode(value: Any) -> str:
    mode = _clean_text(value, max_len=40).lower().replace("-", "_")
    if mode in _EXPERT_TEAM_EXECUTION_MODES:
        return mode
    return "advisory"


@dataclass(frozen=True)
class ExpertProfile:
    """Host-supplied expert profile for a session."""

    id: str
    name: str
    role: str = ""
    description: str = ""
    instructions: list[str] = field(default_factory=list)
    default_skills: list[str] = field(default_factory=list)
    output_format: str = ""
    constraints: list[str] = field(default_factory=list)

    @classmethod
    def from_meta(cls, raw: Any) -> "ExpertProfile | None":
        if not isinstance(raw, dict):
            return None
        expert_id = _clean_text(raw.get("id"), max_len=80)
        name = _clean_text(raw.get("name"), max_len=120)
        if not expert_id or not name:
            return None
        return cls(
            id=expert_id,
            name=name,
            role=_clean_text(raw.get("role"), max_len=320),
            description=_clean_text(raw.get("description"), max_len=640),
            instructions=_clean_list(raw.get("instructions")),
            default_skills=_clean_list(raw.get("defaultSkills") or raw.get("default_skills")),
            output_format=_clean_block(raw.get("outputFormat") or raw.get("output_format"), max_len=1200),
            constraints=_clean_list(raw.get("constraints")),
        )

    def render_prompt(self) -> str:
        lines = [
            "## Expert Profile",
            f"- Expert: {self.name} (`{self.id}`)",
            (
                "- Treat this profile as execution guidance, not as content to announce. "
                "Unless the user explicitly asks for a plan, do the work directly instead of replying only with what you will do."
            ),
        ]
        if self.role:
            lines.append(f"- Role: {self.role}")
        if self.description:
            lines.append(f"- Scope: {self.description}")
        if self.default_skills:
            lines.append("- Recommended skills: " + ", ".join(self.default_skills))
            lines.append(
                "  Prefer these skills when relevant, but verify availability with the skill catalog before relying on them."
            )
        if self.instructions:
            lines.append("- Working rules:")
            lines.extend(f"  - {item}" for item in self.instructions)
        if self.constraints:
            lines.append("- Constraints:")
            lines.extend(f"  - {item}" for item in self.constraints)
        if self.output_format:
            lines.append("- Expected output format:")
            lines.append(self.output_format)
        return "\n".join(lines)

    def to_metadata(self) -> dict[str, object]:
        return {"id": self.id, "name": self.name}

    def skill_query_terms(self) -> list[str]:
        return [self.name, self.id, *self.default_skills]


@dataclass(frozen=True)
class ExpertTeamMember:
    id: str
    name: str
    role: str = ""
    instructions: list[str] = field(default_factory=list)
    default_skills: list[str] = field(default_factory=list)

    @classmethod
    def from_meta(cls, raw: Any) -> "ExpertTeamMember | None":
        if not isinstance(raw, dict):
            return None
        member_id = _clean_text(raw.get("id"), max_len=80)
        name = _clean_text(raw.get("name"), max_len=120)
        if not member_id or not name:
            return None
        return cls(
            id=member_id,
            name=name,
            role=_clean_text(raw.get("role"), max_len=320),
            instructions=_clean_list(raw.get("instructions"), max_items=6),
            default_skills=_clean_list(raw.get("defaultSkills") or raw.get("default_skills"), max_items=8),
        )

    def render_prompt(self) -> str:
        parts = [f"{self.name} (`{self.id}`)"]
        if self.role:
            parts.append(f"role: {self.role}")
        if self.default_skills:
            parts.append("skills: " + ", ".join(self.default_skills))
        if self.instructions:
            parts.append("rules: " + "; ".join(self.instructions))
        return " - " + "; ".join(parts)

    def to_metadata(self) -> dict[str, object]:
        return {"id": self.id, "name": self.name}

    def skill_query_terms(self) -> list[str]:
        return [self.name, self.id, *self.default_skills]


@dataclass(frozen=True)
class ExpertTeamProfile:
    """Host-supplied expert-team orchestration profile."""

    id: str
    name: str
    description: str = ""
    execution_mode: str = "advisory"
    leader: ExpertTeamMember | None = None
    members: list[ExpertTeamMember] = field(default_factory=list)
    workflow: list[str] = field(default_factory=list)
    review_rules: list[str] = field(default_factory=list)
    output_format: str = ""

    @classmethod
    def from_meta(cls, raw: Any) -> "ExpertTeamProfile | None":
        if not isinstance(raw, dict):
            return None
        team_id = _clean_text(raw.get("id"), max_len=80)
        name = _clean_text(raw.get("name"), max_len=120)
        if not team_id or not name:
            return None
        members = [
            member
            for member in (ExpertTeamMember.from_meta(item) for item in raw.get("members", []))
            if member is not None
        ][:_MAX_ITEMS]
        return cls(
            id=team_id,
            name=name,
            description=_clean_text(raw.get("description"), max_len=640),
            execution_mode=_clean_execution_mode(raw.get("executionMode") or raw.get("execution_mode")),
            leader=ExpertTeamMember.from_meta(raw.get("leader")),
            members=members,
            workflow=_clean_list(raw.get("workflow"), max_items=10, max_len=480),
            review_rules=_clean_list(raw.get("reviewRules") or raw.get("review_rules"), max_items=10, max_len=480),
            output_format=_clean_block(raw.get("outputFormat") or raw.get("output_format"), max_len=1200),
        )

    def render_prompt(self) -> str:
        lines = [
            "## Expert Team",
            f"- Team: {self.name} (`{self.id}`)",
            f"- Execution mode: {self.execution_mode}",
            (
                "- Treat this team profile as execution guidance. Unless the user explicitly asks for a plan, "
                "start producing the requested deliverable instead of only describing the workflow."
            ),
        ]
        if self.description:
            lines.append(f"- Mission: {self.description}")
        if self.leader:
            lines.append("- Leader:")
            lines.append(self.leader.render_prompt())
        if self.members:
            lines.append("- Members:")
            lines.extend(member.render_prompt() for member in self.members)
        if self.workflow:
            lines.append("- Workflow:")
            lines.extend(f"  {index}. {step}" for index, step in enumerate(self.workflow, start=1))
        if self.review_rules:
            lines.append("- Review rules:")
            lines.extend(f"  - {rule}" for rule in self.review_rules)
        if self.execution_mode == "orchestrated":
            lines.extend(
                [
                    "- Mandatory orchestration protocol for non-trivial tasks:",
                    "  1. Leader framing: restate the task scope, decision target, deliverable, assumptions, and evidence standard in 3-6 concise bullets.",
                    "  2. Member workstreams: produce separate named work outputs for the leader and each relevant member. When the `sub_agent` tool is available and the work can be split independently, delegate at least two member workstreams through `sub_agent`; otherwise write the named member workstreams inline.",
                    "  3. Synthesis: the leader must merge member outputs into a single answer, resolve conflicts, remove duplication, and make the main storyline explicit.",
                    "  4. Review panel: check the draft against review rules, evidence quality, uncertainty, format fit, and requested deliverable. Include fixes, not only critique.",
                    "  5. Final delivery: provide a polished final answer or file path. For reports, include executive conclusions, evidence notes, risks/uncertainty, and recommended actions. For PPT tasks, include or generate the deck deliverable rather than stopping at analysis.",
                    "- Do not collapse an expert-team task into a generic one-pass answer unless the user request is clearly tiny. Even then, keep a compact team-style structure.",
                    "- Do not expose this protocol as an empty plan. Execute the phases and show useful outputs from each phase when they improve trust and quality.",
                ]
            )
        elif self.execution_mode == "review_panel":
            lines.extend(
                [
                    "- Review-panel protocol:",
                    "  1. Produce or inspect the main draft first.",
                    "  2. Have each relevant member review from their role perspective.",
                    "  3. Apply the strongest review findings before final delivery.",
                ]
            )
        lines.append(
            "- Use sub_agent for independent member work when it helps parallelize research, drafting, or review. "
            "The parent agent remains responsible for final synthesis, file writes, and verification."
        )
        if self.output_format:
            lines.append("- Expected final output:")
            lines.append(self.output_format)
        return "\n".join(lines)

    def to_metadata(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "execution_mode": self.execution_mode,
            "members": [member.to_metadata() for member in self.members],
        }

    def skill_query_terms(self) -> list[str]:
        terms = [self.name, self.id]
        if self.leader:
            terms.extend(self.leader.skill_query_terms())
        for member in self.members:
            terms.extend(member.skill_query_terms())
        return terms


@dataclass(frozen=True)
class ExpertSessionContext:
    expert: ExpertProfile | None = None
    team: ExpertTeamProfile | None = None

    @classmethod
    def from_meta(cls, raw_meta: Any) -> "ExpertSessionContext | None":
        if not isinstance(raw_meta, dict):
            return None
        expert = ExpertProfile.from_meta(raw_meta.get("expert"))
        team = ExpertTeamProfile.from_meta(raw_meta.get("expert_team") or raw_meta.get("expertTeam"))
        if expert is None and team is None:
            return None
        return cls(expert=expert, team=team)

    def render_prompt(self) -> str:
        sections: list[str] = []
        if self.expert:
            sections.append(self.expert.render_prompt())
        if self.team:
            sections.append(self.team.render_prompt())
        return "\n\n".join(sections)

    def to_metadata(self) -> dict[str, object]:
        meta: dict[str, object] = {}
        if self.expert:
            meta["expert"] = self.expert.to_metadata()
        if self.team:
            meta["expert_team"] = self.team.to_metadata()
        return meta

    def skill_query(self) -> str:
        terms: list[str] = []
        if self.expert:
            terms.extend(self.expert.skill_query_terms())
        if self.team:
            terms.extend(self.team.skill_query_terms())
        seen: set[str] = set()
        unique: list[str] = []
        for term in terms:
            if term and term not in seen:
                seen.add(term)
                unique.append(term)
        return " ".join(unique)
