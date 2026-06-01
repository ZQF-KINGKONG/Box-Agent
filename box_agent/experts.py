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


def _clean_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


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
class ExpertTeamWorkflowStage:
    id: str
    title: str
    owner: str = ""
    goal: str = ""
    deliverable: str = ""

    @classmethod
    def from_meta(cls, raw: Any) -> "ExpertTeamWorkflowStage | None":
        if not isinstance(raw, dict):
            return None
        stage_id = _clean_text(raw.get("id"), max_len=80)
        title = _clean_text(raw.get("title"), max_len=120)
        if not stage_id or not title:
            return None
        return cls(
            id=stage_id,
            title=title,
            owner=_clean_text(raw.get("owner"), max_len=120),
            goal=_clean_text(raw.get("goal"), max_len=420),
            deliverable=_clean_text(raw.get("deliverable"), max_len=420),
        )

    def render_prompt(self) -> str:
        parts = [f"{self.title} (`{self.id}`)"]
        if self.owner:
            parts.append(f"owner: {self.owner}")
        if self.goal:
            parts.append(f"goal: {self.goal}")
        if self.deliverable:
            parts.append(f"deliverable: {self.deliverable}")
        return "  - " + "; ".join(parts)

    def to_metadata(self) -> dict[str, object]:
        return {"id": self.id, "title": self.title, "owner": self.owner}

    def skill_query_terms(self) -> list[str]:
        return [self.title, self.owner, self.goal, self.deliverable]


@dataclass(frozen=True)
class ExpertTeamWorkstream:
    member_id: str
    title: str
    brief: str = ""
    deliverable: str = ""
    required: bool = False

    @classmethod
    def from_meta(cls, raw: Any) -> "ExpertTeamWorkstream | None":
        if not isinstance(raw, dict):
            return None
        member_id = _clean_text(raw.get("memberId") or raw.get("member_id"), max_len=80)
        title = _clean_text(raw.get("title"), max_len=120)
        if not member_id or not title:
            return None
        return cls(
            member_id=member_id,
            title=title,
            brief=_clean_text(raw.get("brief"), max_len=520),
            deliverable=_clean_text(raw.get("deliverable"), max_len=520),
            required=_clean_bool(raw.get("required")),
        )

    def render_prompt(self) -> str:
        required = "required" if self.required else "optional"
        parts = [f"{self.title} for `{self.member_id}`", required]
        if self.brief:
            parts.append(f"brief: {self.brief}")
        if self.deliverable:
            parts.append(f"deliverable: {self.deliverable}")
        return "  - " + "; ".join(parts)

    def to_metadata(self) -> dict[str, object]:
        return {
            "member_id": self.member_id,
            "title": self.title,
            "required": self.required,
        }

    def skill_query_terms(self) -> list[str]:
        return [self.member_id, self.title, self.brief, self.deliverable]


@dataclass(frozen=True)
class ExpertTeamOrchestration:
    trigger: str = ""
    stages: list[ExpertTeamWorkflowStage] = field(default_factory=list)
    workstreams: list[ExpertTeamWorkstream] = field(default_factory=list)
    review_checklist: list[str] = field(default_factory=list)

    @classmethod
    def from_meta(cls, raw: Any) -> "ExpertTeamOrchestration | None":
        if not isinstance(raw, dict):
            return None
        stages = [
            stage
            for stage in (ExpertTeamWorkflowStage.from_meta(item) for item in raw.get("stages", []))
            if stage is not None
        ][:_MAX_ITEMS]
        workstreams = [
            stream
            for stream in (ExpertTeamWorkstream.from_meta(item) for item in raw.get("workstreams", []))
            if stream is not None
        ][:_MAX_ITEMS]
        review_checklist = _clean_list(
            raw.get("reviewChecklist") or raw.get("review_checklist"),
            max_items=10,
            max_len=420,
        )
        trigger = _clean_text(raw.get("trigger"), max_len=520)
        if not trigger and not stages and not workstreams and not review_checklist:
            return None
        return cls(
            trigger=trigger,
            stages=stages,
            workstreams=workstreams,
            review_checklist=review_checklist,
        )

    def render_prompt(self) -> str:
        lines = ["- Orchestration contract:"]
        if self.trigger:
            lines.append(f"  - Trigger: {self.trigger}")
        if self.stages:
            lines.append("  - Stages:")
            lines.extend(stage.render_prompt() for stage in self.stages)
        if self.workstreams:
            lines.append("  - Member workstreams:")
            lines.extend(stream.render_prompt() for stream in self.workstreams)
            lines.extend(
                [
                    "  - Delegation task template:",
                    "    Team: <team name and id>",
                    "    Member: <member name and id>",
                    "    Workstream: <workstream title>",
                    "    Objective: <bounded task for this member only>",
                    "    Expected output: <deliverable, evidence notes, assumptions, risks>",
                    "    Constraints: do not write the final combined deliverable; return concise findings for leader synthesis.",
                ]
            )
        if self.review_checklist:
            lines.append("  - Review checklist:")
            lines.extend(f"    - {item}" for item in self.review_checklist)
        return "\n".join(lines)

    def to_metadata(self) -> dict[str, object]:
        return {
            "stage_count": len(self.stages),
            "workstream_count": len(self.workstreams),
            "required_workstreams": [
                stream.to_metadata() for stream in self.workstreams if stream.required
            ],
        }

    def skill_query_terms(self) -> list[str]:
        terms = [self.trigger, *self.review_checklist]
        for stage in self.stages:
            terms.extend(stage.skill_query_terms())
        for stream in self.workstreams:
            terms.extend(stream.skill_query_terms())
        return terms


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
    orchestration: ExpertTeamOrchestration | None = None
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
            orchestration=ExpertTeamOrchestration.from_meta(raw.get("orchestration")),
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
        if self.orchestration:
            lines.append(self.orchestration.render_prompt())
        if self.review_rules:
            lines.append("- Review rules:")
            lines.extend(f"  - {rule}" for rule in self.review_rules)
        if self.execution_mode == "orchestrated":
            if self.orchestration and self.orchestration.workstreams:
                required = [stream.title for stream in self.orchestration.workstreams if stream.required]
                if required:
                    lines.append(
                        "- Required workstreams for non-trivial tasks: " + ", ".join(required)
                    )
            lines.extend(
                [
                    "- Mandatory orchestration protocol for non-trivial tasks:",
                    "  1. Leader framing: restate the task scope, decision target, deliverable, assumptions, and evidence standard in 3-6 concise bullets.",
                    "  2. Member workstreams: produce separate named work outputs for the leader and each relevant member. When the `sub_agent` tool is available and the work can be split independently, delegate the required orchestration workstreams through `sub_agent`; otherwise write the named member workstreams inline.",
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
        meta: dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "execution_mode": self.execution_mode,
            "members": [member.to_metadata() for member in self.members],
        }
        if self.orchestration:
            meta["orchestration"] = self.orchestration.to_metadata()
        return meta

    def skill_query_terms(self) -> list[str]:
        terms = [self.name, self.id]
        if self.leader:
            terms.extend(self.leader.skill_query_terms())
        for member in self.members:
            terms.extend(member.skill_query_terms())
        if self.orchestration:
            terms.extend(self.orchestration.skill_query_terms())
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
