from dataclasses import dataclass, field
from pathlib import Path

from uchrom.im._base import Image2D, Image3D
from uchrom.im.io import load_rounds
from uchrom.im.loc import save_localizations
from uchrom.im.prep.project import project as project_image
from uchrom.im.prep.project import save_projected_array
from uchrom.im.reg import register_global as register_global_rounds
from uchrom.im.reg import register_local as register_local_rounds
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
    traces: object = None
    matrices: object = None
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, manifest, meta=None):
        return cls(raw_rounds=load_rounds(manifest), meta={} if meta is None else dict(meta))

    def project(self, methods=None, z_ranges=None):
        methods = {} if methods is None else methods
        z_ranges = {} if z_ranges is None else z_ranges
        projected = {}

        for round_name, round_spec in self.raw_rounds.items():
            round_methods = methods.get(round_name, {})
            round_z_ranges = z_ranges.get(round_name, {})

            fiducial = round_spec["fiducial"]
            fid_method = round_methods.get("fiducial", "mip")
            fid_zmin, fid_zmax = round_z_ranges.get("fiducial", (None, None))
            projected_images = {}

            for image_name, image in round_spec.get("images", {}).items():
                image_method = round_methods.get(image_name, "mip")
                image_zmin, image_zmax = round_z_ranges.get(image_name, (None, None))
                projected_images[image_name] = Image2D(
                    project_image(image.data, method=image_method, zmin=image_zmin, zmax=image_zmax),
                    name=f"{image.name}_2d",
                    path=None,
                    meta=dict(image.meta),
                )

            projected[round_name] = {
                "fiducial": Image2D(
                    project_image(fiducial.data, method=fid_method, zmin=fid_zmin, zmax=fid_zmax),
                    name=f"{fiducial.name}_2d",
                    path=None,
                    meta=dict(fiducial.meta),
                ),
                "images": projected_images,
                "meta": dict(round_spec.get("meta", {})),
            }

        self.projections = projected
        return projected

    def register_global(self, reference, **kwargs):
        if not self.projections:
            raise ValueError("No projections found. Run workspace.project(...) first.")
        self.global_registration = register_global_rounds(
            self.projections,
            reference=reference,
            **kwargs,
        )
        return self.global_registration

    def register_local(self, reference=None, **kwargs):
        if not self.raw_rounds:
            raise ValueError("No raw rounds found.")
        self.local_registration = register_local_rounds(
            self.raw_rounds,
            global_registration=self.global_registration,
            reference=reference,
            **kwargs,
        )
        return self.local_registration

    def save(self, step, out_dir, mode="selected"):
        if mode in (False, None, "none"):
            return None

        step = str(step)
        out_dir = Path(out_dir)

        if step == "project":
            if not self.projections:
                raise ValueError("No projections found. Run workspace.project(...) first.")
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
