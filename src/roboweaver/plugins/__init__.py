"""
Plugin registry infrastructure (docs/COMPILER_ROADMAP.md Phase 13).

Before this package, every "pick an implementation by name" decision in RoboWeaver
was an if/elif chain (hardware/universal_driver.py::UniversalRobotDriver.connect_robot
being the clearest example) -- adding a new option meant editing that chain rather
than registering one. PluginRegistry replaces the chain with a small, generic,
discoverable registry; Phase 5's CodegenBackend system is its first new consumer.
"""

from roboweaver.plugins.registry import PluginRegistry

__all__ = ["PluginRegistry"]
