from dataclasses import dataclass, field
from pathlib import Path

from uchrom.im.io import load_rounds
from uchrom.im.loc import save_localizations
from uchrom.im.prep.project import project_rounds, save_projected_array
from uchrom.im.reg import register_global as _register_global
from uchrom.im.reg import register_local as _register_local
from uchrom.im.reg import save_local_registration_result
from uchrom.im.reg import save_registration_2d_result
from uchrom.im.seg import save_mask_result
from uchrom.im.trace import save_matrix, save_traces


@dataclass
class ImWorkspace:
    raw_rounds: dict = field(default_factory=dict)
    projections: dict = field(default_factory=dict)
    global_registration: object = None
    local_registration: object = None
    masks: dict = field(default_factory=dict)
    localizations: object = None
    decoded: object = None
    traces: object = None
    matrices: object = None
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, manifest, meta=None):
        return cls(raw_rounds=load_rounds(manifest), meta={} if meta is None else dict(meta))

    def project(self, methods=None, z_ranges=None):
        """Project all raw rounds and store the result in ``self.projections``."""
        self.projections = project_rounds(self.raw_rounds, methods=methods, z_ranges=z_ranges)
        return self.projections

    def register_global(self, reference, **kwargs):
        """Run global 2D registration on projections and store the result."""
        self.global_registration = _register_global(
            self.projections, reference=reference, **kwargs,
        )
        return self.global_registration

    def register_local(self, **kwargs):
        """Run local 3D registration on raw rounds and store the result."""
        if "global_registration" not in kwargs:
            kwargs["global_registration"] = self.global_registration
        self.local_registration = _register_local(
            self.raw_rounds, **kwargs,
        )
        return self.local_registration

    def summary(self):
        return {
            "meta": dict(self.meta),
            "n_rounds": len(self.raw_rounds),
            "rounds": list(self.raw_rounds),
            "n_projected_rounds": len(self.projections),
            "masks": sorted(self.masks),
            "has_global_registration": self.global_registration is not None,
            "has_local_registration": self.local_registration is not None,
            "has_localizations": self.localizations is not None,
            "has_decoded": self.decoded is not None,
            "has_traces": self.traces is not None,
            "has_matrices": self.matrices is not None,
        }

    def save(self, step, out_dir, mode="selected"):
        if mode in (False, None, "none"):
            return None

        step = str(step)
        out_dir = Path(out_dir)

        if step == "project":
            if not self.projections:
                raise ValueError("No projections found. Assign workspace.projections before saving.")
            records = []
            for round_name, round_spec in self.projections.items():
                fiducial = round_spec["fiducial"]
                records.append(
                    {
                        "round": round_name,
                        "role": "fiducial",
                        **save_projected_array(
                            fiducial.data,
                            out_dir=out_dir,
                            out_name=fiducial.name or f"{round_name}_fiducial_2d",
                        ),
                    }
                )
                for image_name, image in round_spec.get("images", {}).items():
                    records.append(
                        {
                            "round": round_name,
                            "role": image_name,
                            **save_projected_array(
                                image.data,
                                out_dir=out_dir,
                                out_name=image.name or f"{round_name}_{image_name}_2d",
                            ),
                        }
                    )
            return records

        if step in ("registration", "global_registration", "register_global"):
            if self.global_registration is None:
                raise ValueError("No global registration result to save.")
            return save_registration_2d_result(
                self.global_registration,
                out_dir=Path(out_dir),
                save=mode,
            )

        if step in ("local_registration", "register_local"):
            if self.local_registration is None:
                raise ValueError("No local registration result to save.")
            return save_local_registration_result(
                self.local_registration,
                out_dir=out_dir,
                save=mode,
            )

        if step in ("mask_2d", "mask_3d"):
            if step not in self.masks:
                raise ValueError(f"No mask result found for '{step}'.")
            return save_mask_result(self.masks[step], out_dir=out_dir, name=step)

        if step in ("localize_3d", "localizations"):
            if self.localizations is None:
                raise ValueError("No localization result to save.")
            return save_localizations(self.localizations, out_dir=out_dir)

        if step in ("tracing", "traces"):
            if self.traces is None:
                raise ValueError("No trace result to save.")
            return save_traces(self.traces, out_dir=out_dir)

        if step == "matrix":
            if self.matrices is None:
                raise ValueError("No matrix result to save.")
            return save_matrix(self.matrices, out_dir=out_dir)

        raise NotImplementedError(f"Saving step '{step}' is not implemented yet.")


__all__ = ["ImWorkspace"]
