from pathlib import Path

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np

from uchrom.im.reg.register_2d import _image_adjust, _normalize_image


REFDIFF_UNCORRECTED_PANEL = (0.125, 0.11, 0.3522727, 0.77)
REFDIFF_CORRECTED_PANEL = (0.5477273, 0.11, 0.3522727, 0.77)
OVERLAY_PANEL = (0.125, 0.11, 0.775, 0.77)


def _crop_abs(image, zoom):
    if zoom is None:
        return image
    y0, y1, x0, x1 = zoom
    if image.ndim == 2:
        return image[y0:y1, x0:x1]
    return image[y0:y1, x0:x1, :]


def _crop_rel(image, box):
    y0, y1, x0, x1 = box
    h, w = image.shape[:2]
    if image.ndim == 2:
        return image[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]
    return image[int(h * y0):int(h * y1), int(w * x0):int(w * x1), :]


def _crop_panel(image, panel_rect, panel_box):
    px, py, pw, ph = panel_rect
    h, w = image.shape[:2]
    x0 = int(w * px)
    x1 = int(w * (px + pw))
    y0 = int(h * py)
    y1 = int(h * (py + ph))
    panel_image = image[y0:y1, x0:x1]
    return _crop_rel(panel_image, panel_box)


def _display_ready(image):
    image = _normalize_image(image)
    image, _, _, _, _ = _image_adjust(
        image,
        lower_threshold=0.5,
        higher_threshold=0.9999,
    )
    return image


def plot_registration_qc_arrays(
    reference_image,
    moving_uncorrected=None,
    moving_corrected=None,
    titles=None,
    zoom=None,
    overlay_gain=1.0,
    moving_round=None,
    reference_round=None,
):
    if hasattr(reference_image, "rounds"):
        result = reference_image
        if moving_round is None:
            raise ValueError(
                "moving_round is required when plotting from a registration result."
            )
        if moving_round not in result.rounds:
            raise ValueError(f"Round '{moving_round}' is not present in registration result.")

        round_result = result.rounds[moving_round]
        reference_round = result.reference if reference_round is None else reference_round
        reference_result = result.rounds[reference_round]

        reference_image = (
            round_result.reference_preprocessed
            if round_result.reference_preprocessed is not None
            else reference_result.registered_fiducial
        )
        moving_uncorrected = (
            round_result.moving_preprocessed
            if round_result.moving_preprocessed is not None
            else round_result.fiducial.data
        )
        moving_corrected = round_result.registered_fiducial

    if moving_uncorrected is None or moving_corrected is None:
        raise ValueError(
            "plot_registration_qc_arrays expects either a registration result plus "
            "moving_round, or reference/moving_uncorrected/moving_corrected arrays."
        )

    ref_disp = _display_ready(reference_image)
    mov_uncorrected_disp = _display_ready(moving_uncorrected)
    mov_corrected_disp = _display_ready(moving_corrected)

    uncorrected = _crop_abs(ref_disp - mov_uncorrected_disp, zoom)
    corrected = _crop_abs(ref_disp - mov_corrected_disp, zoom)
    overlay = _crop_abs(
        np.dstack([ref_disp, mov_corrected_disp, np.zeros_like(ref_disp)]),
        zoom,
    )

    if overlay_gain is not None:
        overlay = np.clip(overlay.astype(np.float32) * overlay_gain, 0, 1)

    if titles is None:
        titles = [
            "Uncorrected",
            "Corrected",
            "Overlay",
        ]

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    axes[0].imshow(uncorrected, cmap="seismic")
    axes[1].imshow(corrected, cmap="seismic")
    axes[2].imshow(overlay)

    for axis, title in zip(axes, titles):
        axis.set_title(title)
        axis.axis("off")

    plt.tight_layout()
    return fig, axes


def plot_registration_qc_png(
    reference_difference_png,
    overlay_corrected_png,
    titles=None,
    panel_box=(1 / 3, 2 / 3, 0.12, 0.58),
    overlay_gain=5.0,
):
    refdiff = mpimg.imread(str(Path(reference_difference_png)))
    overlay = mpimg.imread(str(Path(overlay_corrected_png)))

    uncorrected = _crop_panel(refdiff, REFDIFF_UNCORRECTED_PANEL, panel_box)
    corrected = _crop_panel(refdiff, REFDIFF_CORRECTED_PANEL, panel_box)
    overlay_img = _crop_panel(overlay, OVERLAY_PANEL, panel_box)

    if overlay_gain is not None:
        overlay_img = np.clip(overlay_img.astype(np.float32) * overlay_gain, 0, 1)

    if titles is None:
        titles = [
            "Uncorrected - zoom",
            "Corrected - zoom",
            "Overlay - zoom",
        ]

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    axes[0].imshow(uncorrected)
    axes[1].imshow(corrected)
    axes[2].imshow(overlay_img)

    for axis, title in zip(axes, titles):
        axis.set_title(title)
        axis.axis("off")

    plt.tight_layout()
    return fig, axes


__all__ = [
    "plot_registration_qc_arrays",
    "plot_registration_qc_png",
]
