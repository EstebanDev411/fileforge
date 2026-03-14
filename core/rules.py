"""
core/rules.py
--------------
Custom rules engine for FileForge.

Rules are evaluated BEFORE the standard classifier and heuristics.
If a rule matches, it sets the file's destination and skips further
classification — rules always win.

Rule structure (stored in config/rules.json)
--------------------------------------------
    {
      "id": "uuid",
      "name": "Invoices to Accounting",
      "enabled": true,
      "priority": 10,          ← lower = higher priority
      "conditions": [
        {"field": "name",      "op": "contains",    "value": "factura"},
        {"field": "extension", "op": "in",          "value": ".pdf,.docx"},
        {"field": "size",      "op": "greater_than", "value": 1048576}
      ],
      "condition_logic": "ANY",  ← "ALL" (and) | "ANY" (or)
      "action": {
        "type": "move_to",
        "destination": "Documents/Accounting/Invoices"
      }
    }

Supported fields
----------------
  name        — filename without extension  (str)
  filename    — full filename with extension (str)
  extension   — file extension (.pdf, .jpg…) (str)
  size        — file size in bytes           (int)
  modified    — last modified (days ago)     (float)
  created     — creation date (days ago)     (float)
  path        — full absolute path           (str)
  category    — category after classification (str)

Supported operators
-------------------
  contains        — substring match (case-insensitive)
  not_contains    — inverse of contains
  starts_with     — prefix match
  ends_with       — suffix match
  equals          — exact match (case-insensitive)
  not_equals
  in              — comma-separated list of values
  not_in
  greater_than    — numeric comparison
  less_than
  greater_eq
  less_eq
  regex           — full regex match

Supported actions
-----------------
  move_to         — set sub_category to given path (organizer does the actual move)
  rename_prefix   — prepend a string to the filename
  rename_suffix   — append a string before the extension
  skip            — mark file to be skipped entirely

Usage
-----
    from core.rules import RulesEngine

    engine = RulesEngine()
    engine.load()

    matched, rule_name = engine.apply(entry)
    # entry.sub_category is now set if a rule matched
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from system.config import Config
from system.logger import get_logger

log = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
#  Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Condition:
    field: str              # name | filename | extension | size | path | category | modified | created
    op:    str              # contains | equals | in | greater_than | regex | …
    value: str              # raw string — interpreted based on field + op


@dataclass
class Action:
    type:        str        # move_to | rename_prefix | rename_suffix | skip
    destination: str = ""  # used by move_to (e.g. "Documents/Invoices")
    value:       str = ""  # used by rename_prefix / rename_suffix


@dataclass
class Rule:
    id:              str
    name:            str
    enabled:         bool            = True
    priority:        int             = 50
    conditions:      list[Condition] = field(default_factory=list)
    condition_logic: str             = "ALL"    # ALL | ANY
    action:          Optional[Action] = None

    def to_dict(self) -> dict:
        return {
            "id":              self.id,
            "name":            self.name,
            "enabled":         self.enabled,
            "priority":        self.priority,
            "conditions":      [{"field": c.field, "op": c.op, "value": c.value}
                                 for c in self.conditions],
            "condition_logic": self.condition_logic,
            "action":          {"type": self.action.type,
                                 "destination": self.action.destination,
                                 "value": self.action.value}
                                 if self.action else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        conditions = [
            Condition(field=c["field"], op=c["op"], value=c["value"])
            for c in d.get("conditions", [])
        ]
        action_d = d.get("action") or {}
        action = Action(
            type=action_d.get("type", "move_to"),
            destination=action_d.get("destination", ""),
            value=action_d.get("value", ""),
        ) if action_d else None

        return cls(
            id=d.get("id", str(uuid.uuid4())),
            name=d.get("name", "Unnamed rule"),
            enabled=d.get("enabled", True),
            priority=d.get("priority", 50),
            conditions=conditions,
            condition_logic=d.get("condition_logic", "ALL"),
            action=action,
        )


# ──────────────────────────────────────────────────────────────────────────────
#  Rules storage path
# ──────────────────────────────────────────────────────────────────────────────

def _rules_path() -> Path:
    try:
        from paths import Paths
        p = Paths.writable_root() / "config" / "rules.json"
    except ImportError:
        p = Path(__file__).parent.parent / "config" / "rules.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ──────────────────────────────────────────────────────────────────────────────
#  Rules Engine
# ──────────────────────────────────────────────────────────────────────────────

class RulesEngine:
    """
    Loads, evaluates and manages custom rules.

    Rules are sorted by priority (ascending) before evaluation.
    The first matching rule wins — subsequent rules are not checked.
    """

    def __init__(self):
        self._rules: list[Rule] = []
        self.load()

    # ------------------------------------------------------------------ #
    #  Persistence                                                          #
    # ------------------------------------------------------------------ #

    def load(self) -> None:
        """Load rules from rules.json. Silently creates empty list if missing."""
        path = _rules_path()
        if not path.exists():
            self._rules = []
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._rules = [Rule.from_dict(d) for d in data.get("rules", [])]
            log.info("RulesEngine: loaded %d rules from %s", len(self._rules), path)
        except Exception as exc:
            log.error("RulesEngine: failed to load rules: %s", exc)
            self._rules = []

    def save(self) -> None:
        """Persist current rules to rules.json."""
        path = _rules_path()
        data = {"rules": [r.to_dict() for r in self._rules]}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        log.info("RulesEngine: saved %d rules", len(self._rules))

    def reload(self) -> None:
        self.load()

    # ------------------------------------------------------------------ #
    #  Rule management                                                      #
    # ------------------------------------------------------------------ #

    def add_rule(self, rule: Rule) -> None:
        if not rule.id:
            rule.id = str(uuid.uuid4())
        self._rules.append(rule)

    def remove_rule(self, rule_id: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.id != rule_id]
        return len(self._rules) < before

    def update_rule(self, rule: Rule) -> None:
        for i, r in enumerate(self._rules):
            if r.id == rule.id:
                self._rules[i] = rule
                return
        self._rules.append(rule)

    def get_rule(self, rule_id: str) -> Optional[Rule]:
        for r in self._rules:
            if r.id == rule_id:
                return r
        return None

    def all_rules(self) -> list[Rule]:
        """Return rules sorted by priority."""
        return sorted(self._rules, key=lambda r: r.priority)

    def enabled_rules(self) -> list[Rule]:
        return [r for r in self.all_rules() if r.enabled]

    # ------------------------------------------------------------------ #
    #  Evaluation                                                           #
    # ------------------------------------------------------------------ #

    def apply(self, entry) -> tuple[bool, str]:
        """
        Evaluate all enabled rules against a FileEntry.

        If a rule matches, mutate entry.sub_category (and optionally
        entry.name) according to the action, then return (True, rule_name).

        Returns (False, "") if no rule matched.
        """
        for rule in self.enabled_rules():
            if self._matches(rule, entry):
                self._execute(rule, entry)
                log.debug("Rule '%s' matched: %s", rule.name, entry.name)
                return True, rule.name
        return False, ""

    def apply_all(self, entries: list) -> dict[str, int]:
        """
        Apply rules to all entries.
        Returns {"matched": N, "skipped": N, "total": N}.
        """
        matched = skipped = 0
        for entry in entries:
            hit, rule_name = self.apply(entry)
            if hit:
                if getattr(entry, "_rule_skip", False):
                    skipped += 1
                else:
                    matched += 1
        log.info(
            "RulesEngine.apply_all: %d matched, %d skipped (of %d)",
            matched, skipped, len(entries),
        )
        return {"matched": matched, "skipped": skipped, "total": len(entries)}

    def test_rule(self, rule: Rule, entries: list) -> list[str]:
        """
        Dry-run: return list of filenames that would match the rule.
        Does NOT mutate entries.
        """
        return [e.name for e in entries if self._matches(rule, e)]

    # ------------------------------------------------------------------ #
    #  Match logic                                                          #
    # ------------------------------------------------------------------ #

    def _matches(self, rule: Rule, entry) -> bool:
        if not rule.conditions:
            return False

        results = [self._eval_condition(c, entry) for c in rule.conditions]

        if rule.condition_logic == "ANY":
            return any(results)
        return all(results)   # ALL (default)

    def _eval_condition(self, cond: Condition, entry) -> bool:
        raw = self._get_field_value(cond.field, entry)
        op  = cond.op
        val = cond.value

        try:
            # ── String operators ─────────────────────────────────────
            if op == "contains":
                return val.lower() in str(raw).lower()
            if op == "not_contains":
                return val.lower() not in str(raw).lower()
            if op == "starts_with":
                return str(raw).lower().startswith(val.lower())
            if op == "ends_with":
                return str(raw).lower().endswith(val.lower())
            if op == "equals":
                return str(raw).lower() == val.lower()
            if op == "not_equals":
                return str(raw).lower() != val.lower()
            if op == "in":
                items = [v.strip().lower() for v in val.split(",")]
                return str(raw).lower() in items
            if op == "not_in":
                items = [v.strip().lower() for v in val.split(",")]
                return str(raw).lower() not in items
            if op == "regex":
                return bool(re.search(val, str(raw), re.IGNORECASE))

            # ── Numeric operators ────────────────────────────────────
            num = float(raw) if raw is not None else 0.0
            threshold = float(val)
            if op == "greater_than": return num > threshold
            if op == "less_than":    return num < threshold
            if op == "greater_eq":   return num >= threshold
            if op == "less_eq":      return num <= threshold

        except (TypeError, ValueError, re.error) as exc:
            log.debug("Condition eval error (%s %s %s): %s", cond.field, op, val, exc)

        return False

    @staticmethod
    def _get_field_value(field: str, entry) -> Any:
        """Extract a field value from a FileEntry."""
        p = Path(entry.path)
        now = time.time()

        if field == "name":           return p.stem
        if field == "filename":       return entry.name
        if field == "extension":      return entry.extension.lower()
        if field == "size":           return entry.size
        if field == "path":           return entry.path
        if field == "category":       return getattr(entry, "category", "")
        if field == "modified":       return (now - entry.modified) / 86400   # days ago
        if field == "created":        return (now - entry.created)  / 86400
        return ""

    # ------------------------------------------------------------------ #
    #  Action execution                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _execute(rule: Rule, entry) -> None:
        if not rule.action:
            return

        action = rule.action

        if action.type == "move_to":
            entry.sub_category = action.destination.strip("/")

        elif action.type == "skip":
            entry._rule_skip = True
            entry.sub_category = "__SKIP__"

        elif action.type == "rename_prefix":
            p = Path(entry.path)
            entry.name = action.value + entry.name
            entry.path = str(p.parent / entry.name)

        elif action.type == "rename_suffix":
            p = Path(entry.path)
            stem = p.stem
            entry.name = stem + action.value + entry.extension
            entry.path = str(p.parent / entry.name)


# ──────────────────────────────────────────────────────────────────────────────
#  Preset rule templates (shown in GUI "Add from template")
# ──────────────────────────────────────────────────────────────────────────────

RULE_TEMPLATES: list[dict] = [
    {
        "name": "Invoices → Documents/Invoices",
        "conditions": [{"field": "name", "op": "contains", "value": "factura,invoice,bill,receipt"}],
        "condition_logic": "ANY",
        "action": {"type": "move_to", "destination": "Documents/Invoices"},
    },
    {
        "name": "WhatsApp media → Social",
        "conditions": [{"field": "path", "op": "contains", "value": "WhatsApp"}],
        "condition_logic": "ALL",
        "action": {"type": "move_to", "destination": "Images/Social/WhatsApp"},
    },
    {
        "name": "Large videos (>500 MB) → LargeVideos",
        "conditions": [
            {"field": "extension", "op": "in",           "value": ".mp4,.mkv,.avi,.mov"},
            {"field": "size",      "op": "greater_than", "value": "524288000"},
        ],
        "condition_logic": "ALL",
        "action": {"type": "move_to", "destination": "_LargeFiles/Videos"},
    },
    {
        "name": "Old files (>365 days) → Archive",
        "conditions": [{"field": "modified", "op": "greater_than", "value": "365"}],
        "condition_logic": "ALL",
        "action": {"type": "move_to", "destination": "_Archive"},
    },
    {
        "name": "Work documents → Work",
        "conditions": [
            {"field": "extension", "op": "in", "value": ".pdf,.docx,.xlsx,.pptx"},
            {"field": "name",      "op": "not_contains", "value": "personal"},
        ],
        "condition_logic": "ALL",
        "action": {"type": "move_to", "destination": "Documents/Work"},
    },
    {
        "name": "Skip temp files",
        "conditions": [{"field": "extension", "op": "in", "value": ".tmp,.temp,.bak,.~"}],
        "condition_logic": "ANY",
        "action": {"type": "skip", "destination": ""},
    },
]
