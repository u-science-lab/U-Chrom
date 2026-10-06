"""Single-cell 3-D genome reconstruction.

* :func:`reconstruct_ember` — EMber, noise-aware reconstruction (native engine, protocol ``"robust"``);
* :func:`reconstruct_nucdyn` — NucDynamics (native engine; protocols ``"nuc_dynamics_2017"``,
  ``"release_1.3"``, ``"robust"`` / ``"ember"``).

Both import the native engine (``uchrom_nucdyn``) only when called.
"""


def __getattr__(name):
    if name == "reconstruct_ember":
        from .ember import reconstruct_ember

        return reconstruct_ember
    if name == "reconstruct_nucdyn":
        from .nucdyn import reconstruct_nucdyn

        return reconstruct_nucdyn
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["reconstruct_ember", "reconstruct_nucdyn"]
