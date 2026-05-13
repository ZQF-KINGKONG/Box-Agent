"""
Skill Loader - Load Claude Skills from multiple sources.

Supports:
- Builtin skills shipped with the package (read-only)
- User skills at ~/.box-agent/skills/ (writable from officev3)
- User skills override builtin ones on name conflict
- mtime-based auto reload (no explicit trigger needed)
- Manifest-based whitelist for builtin sources: any SKILL.md left on disk
  (e.g. by a downstream host that updated box-agent without deleting old
  files) but absent from ``_manifest.json`` is ignored as an orphan.
"""

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional, Set, Tuple

import yaml

SkillSource = Literal["builtin", "user"]

MANIFEST_FILENAME = "_manifest.json"


def _warn(msg: str) -> None:
    """Write diagnostic message to stderr (never stdout)."""
    sys.stderr.write(msg + "\n")


@dataclass
class Skill:
    """Skill data structure"""

    name: str
    description: str
    content: str
    source: SkillSource = "builtin"
    license: Optional[str] = None
    allowed_tools: Optional[List[str]] = None
    metadata: Optional[Dict[str, str]] = None
    skill_path: Optional[Path] = None

    def to_prompt(self) -> str:
        """Convert skill to prompt format"""
        skill_root = str(self.skill_path.parent) if self.skill_path else "unknown"

        return f"""
# Skill: {self.name}

{self.description}

**Skill Root Directory:** `{skill_root}`

All files and references in this skill are relative to this directory.

---

{self.content}
"""

    def to_metadata_dict(self) -> Dict[str, object]:
        """Structured metadata for officev3 / ACP _meta payloads."""
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "path": str(self.skill_path) if self.skill_path else None,
        }


@dataclass
class _SourceEntry:
    """Internal: a single skills source directory with a label."""

    directory: Path
    source: SkillSource
    last_mtime: float = 0.0
    signature: Tuple[Tuple[str, int, int], ...] = field(default_factory=tuple)
    # Optional whitelist of skill names. None means "no manifest, accept all".
    # Empty set means "manifest present but lists zero skills" → load nothing.
    manifest_names: Optional[Set[str]] = None
    # Optional manifest-listed SKILL.md paths. None means "scan with rglob".
    manifest_paths: Optional[Tuple[Path, ...]] = None
    manifest_loaded: bool = False


class SkillLoader:
    """Skill loader supporting multiple prioritized sources."""

    def __init__(
        self,
        sources: Optional[List[Tuple[str | Path, SkillSource]] | str | Path] = None,
        skills_dir: Optional[str] = None,
    ):
        """
        Initialize Skill Loader.

        Args:
            sources: Ordered list of (directory, source_label) tuples. Earlier
                entries take priority on name conflicts. Also accepts a single
                str/Path for legacy single-directory usage (treated as
                "builtin" source).
            skills_dir: Legacy single-directory keyword. Treated as a single
                "builtin" source when sources is not provided.
        """
        if isinstance(sources, (str, Path)):
            sources = [(sources, "builtin")]
        elif sources is None:
            legacy = skills_dir or "./skills"
            sources = [(legacy, "builtin")]

        self._sources: List[_SourceEntry] = [
            _SourceEntry(directory=Path(d).expanduser(), source=s) for d, s in sources
        ]
        self.loaded_skills: Dict[str, Skill] = {}

    # Backward compatibility — expose the first source directory
    @property
    def skills_dir(self) -> Path:
        return self._sources[0].directory if self._sources else Path("./skills")

    def load_skill(self, skill_path: Path, source: SkillSource = "builtin") -> Optional[Skill]:
        """Load a single skill from a SKILL.md file."""
        try:
            content = skill_path.read_text(encoding="utf-8")

            frontmatter_match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
            if not frontmatter_match:
                _warn(f"⚠️  {skill_path} missing YAML frontmatter")
                return None

            frontmatter_text = frontmatter_match.group(1)
            skill_content = frontmatter_match.group(2).strip()

            try:
                frontmatter = yaml.safe_load(frontmatter_text)
            except yaml.YAMLError as e:
                _warn(f"❌ Failed to parse YAML frontmatter: {e}")
                return None

            if "name" not in frontmatter or "description" not in frontmatter:
                _warn(f"⚠️  {skill_path} missing required fields (name or description)")
                return None

            skill_dir = skill_path.parent
            processed_content = self._process_skill_paths(skill_content, skill_dir)

            return Skill(
                name=frontmatter["name"],
                description=frontmatter["description"],
                content=processed_content,
                source=source,
                license=frontmatter.get("license"),
                allowed_tools=frontmatter.get("allowed-tools"),
                metadata=frontmatter.get("metadata"),
                skill_path=skill_path,
            )

        except Exception as e:
            _warn(f"❌ Failed to load skill ({skill_path}): {e}")
            return None

    def _process_skill_paths(self, content: str, skill_dir: Path) -> str:
        """Replace relative paths in skill content with absolute paths."""
        import re

        def replace_dir_path(match):
            prefix = match.group(1)
            rel_path = match.group(2)
            abs_path = skill_dir / rel_path
            if abs_path.exists():
                return f"{prefix}{abs_path}"
            return match.group(0)

        pattern_dirs = r"(python\s+|`)((?:scripts|references|assets)/[^\s`\)]+)"
        content = re.sub(pattern_dirs, replace_dir_path, content)

        def replace_doc_path(match):
            prefix = match.group(1)
            filename = match.group(2)
            suffix = match.group(3)
            abs_path = skill_dir / filename
            if abs_path.exists():
                return f"{prefix}`{abs_path}` (use read_file to access){suffix}"
            return match.group(0)

        pattern_docs = r"(see|read|refer to|check)\s+([a-zA-Z0-9_-]+\.(?:md|txt|json|yaml))([.,;\s])"
        content = re.sub(pattern_docs, replace_doc_path, content, flags=re.IGNORECASE)

        def replace_markdown_link(match):
            prefix = match.group(1) if match.group(1) else ""
            link_text = match.group(2)
            filepath = match.group(3)
            clean_path = filepath[2:] if filepath.startswith("./") else filepath
            abs_path = skill_dir / clean_path
            if abs_path.exists():
                return f"{prefix}[{link_text}](`{abs_path}`) (use read_file to access)"
            return match.group(0)

        pattern_markdown = (
            r"(?:(Read|See|Check|Refer to|Load|View)\s+)?\[(`?[^`\]]+`?)\]"
            r"\(((?:\./)?[^)]+\.(?:md|txt|json|yaml|js|py|html))\)"
        )
        content = re.sub(pattern_markdown, replace_markdown_link, content, flags=re.IGNORECASE)

        return content

    def discover_skills(self) -> List[Skill]:
        """Discover skills from all sources; user overrides builtin on name conflict."""
        self.loaded_skills = {}
        discovered: List[Skill] = []

        # Reverse order: load lower-priority sources first, then higher-priority
        # ones overwrite by dict assignment.
        for entry in reversed(self._sources):
            if not entry.directory.exists():
                continue

            # Manifest only applies to builtin sources. For user skills we
            # never want to hide SKILL.md files the user (or officev3) dropped
            # in at runtime.
            if entry.source == "builtin":
                self._load_manifest(entry)

            for skill_file in self._iter_skill_files(entry):
                skill = self.load_skill(skill_file, source=entry.source)
                if skill is None:
                    continue

                if (
                    entry.source == "builtin"
                    and entry.manifest_names is not None
                    and skill.name not in entry.manifest_names
                ):
                    _warn(
                        f"⚠️  Ignoring orphan builtin skill '{skill.name}' at "
                        f"{skill_file} (not listed in {MANIFEST_FILENAME}). "
                        f"This usually means a previous box-agent version "
                        f"shipped the skill and the current installer left "
                        f"the files behind."
                    )
                    continue

                self.loaded_skills[skill.name] = skill

            # Cache a cheap signature for reload detection. Keep last_mtime for
            # backward compatibility with older tests/debug code that may read it.
            entry.signature = self._source_signature(entry)
            entry.last_mtime = max((mtime for _, mtime, _ in entry.signature), default=0) / 1_000_000_000

        discovered = list(self.loaded_skills.values())
        return discovered

    def _iter_skill_files(self, entry: _SourceEntry) -> List[Path]:
        """Return candidate SKILL.md files for one source.

        Builtin package skills usually ship a manifest with explicit paths; use
        it to avoid walking large resource trees such as OOXML schemas or JS
        bundles on every discovery. User skills keep recursive discovery so
        officev3-authored skills are picked up without regenerating a manifest.
        """
        if (
            entry.source == "builtin"
            and entry.manifest_names is not None
            and entry.manifest_paths is not None
        ):
            return [path for path in entry.manifest_paths if path.is_file()]

        return list(entry.directory.rglob("SKILL.md"))

    def _load_manifest(self, entry: _SourceEntry) -> None:
        """Populate ``entry.manifest_names`` from ``_manifest.json`` if present.

        Missing manifest → ``manifest_names`` stays ``None`` (no filtering),
        preserving backward compatibility with builtin skills directories that
        pre-date the manifest (dev trees, third-party bundles, etc.).
        """

        manifest_path = entry.directory / MANIFEST_FILENAME
        if not manifest_path.is_file():
            entry.manifest_names = None
            entry.manifest_paths = None
            entry.manifest_loaded = True
            return

        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _warn(
                f"⚠️  Failed to read builtin skills manifest at {manifest_path}: {exc}. "
                f"Falling back to unfiltered discovery."
            )
            entry.manifest_names = None
            entry.manifest_paths = None
            entry.manifest_loaded = True
            return

        raw_skills = data.get("skills") if isinstance(data, dict) else None
        if not isinstance(raw_skills, list):
            _warn(
                f"⚠️  Builtin skills manifest {manifest_path} is malformed "
                f"(missing 'skills' list); falling back to unfiltered discovery."
            )
            entry.manifest_names = None
            entry.manifest_paths = None
            entry.manifest_loaded = True
            return

        names: Set[str] = set()
        paths: list[Path] = []
        all_paths_known = True
        for item in raw_skills:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                names.add(item["name"])
                raw_path = item.get("path")
                if isinstance(raw_path, str) and raw_path.strip():
                    paths.append(entry.directory / raw_path)
                else:
                    all_paths_known = False
            elif isinstance(item, str):
                names.add(item)
                all_paths_known = False
        entry.manifest_names = names
        entry.manifest_paths = tuple(paths) if all_paths_known else None
        entry.manifest_loaded = True

    @staticmethod
    def _stat_signature(path: Path, root: Path) -> tuple[str, int, int] | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = str(path)
        return (rel, stat.st_mtime_ns, stat.st_size)

    def _source_signature(self, entry: _SourceEntry) -> Tuple[Tuple[str, int, int], ...]:
        """Return a lightweight signature for files that affect skill loading."""
        if not entry.directory.exists():
            return ()

        candidates: list[Path] = []
        manifest = entry.directory / MANIFEST_FILENAME
        if manifest.is_file():
            candidates.append(manifest)

        if (
            entry.source == "builtin"
            and entry.manifest_names is not None
            and entry.manifest_paths is not None
        ):
            candidates.extend(entry.manifest_paths)
        else:
            candidates.extend(entry.directory.rglob("SKILL.md"))

        signatures = [
            signature
            for path in candidates
            if (signature := self._stat_signature(path, entry.directory)) is not None
        ]
        return tuple(sorted(signatures))

    @staticmethod
    def _dir_mtime(directory: Path) -> float:
        """Return the max mtime across the directory tree (cheap recursive stat).

        Used to detect added/removed/modified skill files.
        """
        if not directory.exists():
            return 0.0
        try:
            latest = directory.stat().st_mtime
            for path in directory.rglob("*"):
                try:
                    mt = path.stat().st_mtime
                    if mt > latest:
                        latest = mt
                except OSError:
                    continue
            return latest
        except OSError:
            return 0.0

    def maybe_reload(self) -> bool:
        """Reload skills if any source directory's mtime has changed.

        Returns:
            True if a reload was performed, False otherwise.
        """
        changed = False
        for entry in self._sources:
            current = self._source_signature(entry)
            if current != entry.signature:
                changed = True
                break

        if changed:
            self.discover_skills()
        return changed

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a loaded skill by name."""
        return self.loaded_skills.get(name)

    def list_skills(self) -> List[str]:
        """List all loaded skill names."""
        return list(self.loaded_skills.keys())

    def list_skills_metadata(self) -> List[Dict[str, object]]:
        """Return structured metadata for every loaded skill.

        Intended for officev3 / ACP `_meta.skills` payloads.
        """
        return [skill.to_metadata_dict() for skill in self.loaded_skills.values()]

    def get_skills_metadata_prompt(self) -> str:
        """Generate a metadata-only prompt for Progressive Disclosure Level 1."""
        if not self.loaded_skills:
            return ""

        prompt_parts = ["## Available Skills\n"]
        prompt_parts.append(
            "You have access to specialized skills. Each skill provides expert guidance for specific tasks.\n"
        )
        prompt_parts.append(
            "Load a skill's full content using the appropriate skill tool when needed.\n"
        )

        # Tell the model the canonical skill directories so it does not invent
        # paths or scan unrelated parts of the disk when the user asks where
        # skills live.
        if self._sources:
            prompt_parts.append("**Skill source directories (the ONLY places skills are loaded from):**")
            for entry in self._sources:
                prompt_parts.append(f"- `{entry.source}`: `{entry.directory}`")
            prompt_parts.append(
                "Do NOT search any other directory for skills. "
                "If the user asks where skills are stored, answer with the paths above. "
                "Custom skills should be added under the `user` source directory."
            )
            prompt_parts.append("")

        prompt_parts.append("**Skill catalog:**")
        for skill in self.loaded_skills.values():
            prompt_parts.append(f"- `{skill.name}` ({skill.source}): {skill.description}")

        return "\n".join(prompt_parts)
