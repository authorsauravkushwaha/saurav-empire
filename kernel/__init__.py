"""SAURAV AI CIVILIZATION — kernel.

The kernel is the shared brain imported by every service, agent, and script.
It owns: paths, config, storage, event bus, governance (truth + ethics + approvals),
naming, the model router, the agent runtime, the university, and the economic engine.

Design rules:
  * Standard library first. Third-party packages are optional upgrades.
  * Local-first: the kernel boots and works with no network and no LLM.
  * Honest: nothing is stamped "verified" unless something verified it.
"""

__version__ = "1.0.0"
__all__ = ["paths", "config", "store", "eventbus", "governance", "naming", "model_router", "registry"]
