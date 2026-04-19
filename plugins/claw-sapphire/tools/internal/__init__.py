"""Internal Sapphire tools — invoked programmatically, not agent-facing.

These scripts back the `status: internal` entries in
`infra/tool-registry.yaml`. Thin shims at `../{name}.py` preserve the
historical `plugins/claw-sapphire/tools/{name}.py` invocation path used by
scheduled tasks and hermes skills.
"""
