"""``uchrom.settings`` is :mod:`chromdata.settings` (the memory budget of out-of-core work): the same ``settings``
object for the data model and the analysis library, so ``uchrom.settings.memory_budget = "8GB"`` bounds both."""

from chromdata.settings import Settings, _available_ram, format_bytes, parse_bytes, settings  # noqa: F401
