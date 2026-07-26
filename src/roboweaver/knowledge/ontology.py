"""Robotics Knowledge Graph Ontology definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeType(Enum):
    SKILL = "SKILL"
    TOOL = "TOOL"
    OBJECT = "OBJECT"
    CONSTRAINT = "CONSTRAINT"
    ENVIRONMENT = "ENVIRONMENT"
    ROBOT = "ROBOT"
    PACKAGE = "PACKAGE"
    MIDDLEWARE = "MIDDLEWARE"
    SENSOR = "SENSOR"


class RelationType(Enum):
    REQUIRES_TOOL = "REQUIRES_TOOL"
    SUITABLE_FOR = "SUITABLE_FOR"
    HAS_CONSTRAINT = "HAS_CONSTRAINT"
    SUBTASK_OF = "SUBTASK_OF"
    COMPATIBLE_WITH = "COMPATIBLE_WITH"
    TARGETS_OBJECT = "TARGETS_OBJECT"
    REQUIRES_PACKAGE = "REQUIRES_PACKAGE"
    IMPLEMENTS_SKILL = "IMPLEMENTS_SKILL"
    INTERFACES_WITH = "INTERFACES_WITH"


@dataclass
class KnowledgeNode:
    """A node in the Robotics Knowledge Graph."""
    id: str
    name: str
    type: NodeType
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeEdge:
    """A directed edge in the Robotics Knowledge Graph."""
    source_id: str
    target_id: str
    relation: RelationType
    properties: dict[str, Any] = field(default_factory=dict)
