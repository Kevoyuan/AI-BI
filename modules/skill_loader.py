"""
Skill Loader
Reads skill definitions from the skills/ directory.
Each skill is a folder containing:
  - skill.yaml  (metadata: name, description, type)
  - prompt.md   (LLM system prompt)
  - scripts/    (optional Python helper scripts)
"""
import os
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List

import yaml

logger = logging.getLogger(__name__)

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "skills")


@dataclass
class Skill:
    name: str
    description: str
    skill_type: str          # "text" | "code"
    prompt: str = ""
    tags: List[str] = field(default_factory=list)


class SkillRegistry:
    """
    Scans the skills/ directory on first access and caches all skill
    definitions. Adding a new skill folder is enough to make it routable.
    """

    _instance: Optional["SkillRegistry"] = None
    _skills: Dict[str, Skill] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        skills_root = os.path.abspath(SKILLS_DIR)
        if not os.path.isdir(skills_root):
            logger.warning("Skills directory not found: %s", skills_root)
            return

        for skill_dir in sorted(os.listdir(skills_root)):
            path = os.path.join(skills_root, skill_dir)
            if not os.path.isdir(path):
                continue

            meta_path   = os.path.join(path, "skill.yaml")
            prompt_path = os.path.join(path, "prompt.md")

            if not os.path.exists(meta_path):
                continue

            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = yaml.safe_load(f)

                prompt = ""
                if os.path.exists(prompt_path):
                    with open(prompt_path, encoding="utf-8") as f:
                        prompt = f.read()

                skill = Skill(
                    name=meta.get("name", skill_dir),
                    description=meta.get("description", ""),
                    skill_type=meta.get("type", "text"),
                    prompt=prompt,
                    tags=meta.get("tags", []),
                )
                self._skills[skill_dir] = skill
                logger.info("Loaded skill: %s (type=%s)", skill_dir, skill.skill_type)

            except Exception as exc:
                logger.warning("Failed to load skill '%s': %s", skill_dir, exc)

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def get_skill_prompt(self, name: str) -> str:
        skill = self._skills.get(name)
        return skill.prompt if skill else ""

    def list_skills(self) -> List[str]:
        return list(self._skills.keys())
