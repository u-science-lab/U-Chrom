import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from uchrom.im._pyhim import get_spot_properties, segment_spots_3d_stardist
from uchrom.im.loc import localize
from uchrom.im.seg import segment


class TestPyHiMBackends(unittest.TestCase):
    def test_pyhim_2d_mask_inhomogeneous_runs(self):
        image = np.zeros((64, 64), dtype=float)
        image[16:24, 16:24] = 8.0
        image[40:49, 38:47] = 10.0

        result = segment(
            image,
            method="pyhim",
            background_method="inhomogeneous",
            tessellation=False,
            area_min=4,
            area_max=500,
        )

        self.assertEqual(result.labels.shape, image.shape)
        self.assertGreaterEqual(int(result.labels.max()), 2)

    def test_pyhim_3d_localize_thresholding_runs(self):
        stack = np.zeros((9, 64, 64), dtype=float)
        stack[3:6, 16:24, 18:26] = 20.0
        stack[4:7, 36:44, 36:44] = 18.0
        stack[2:5, 8:14, 8:14] = 10.0

        result = localize(
            {"RT26": stack},
            method="pyhim_3d",
            backend="thresholding",
            reduce_planes=False,
            threshold_over_std=2.0,
            area_min=2,
            area_max=500,
            brightest=100,
            subpixel_refine=False,
            z_binning=2,
        )

        self.assertFalse(result.table.empty)
        self.assertTrue({"Barcode #", "zcentroid", "xcentroid", "ycentroid"}.issubset(result.table.columns))
        self.assertTrue((result.table["Barcode #"] == 26).all())

    def test_pyhim_2d_mask_stardist_keeps_model_metadata_and_raw_labels(self):
        image = np.zeros((48, 48), dtype=np.float32)
        image[12:20, 12:20] = 4.0
        image[26:34, 24:32] = 5.0

        class DummyStarDist2D:
            def __init__(self, *args, **kwargs):
                pass

            def predict_instances(self, normalized):
                labeled = np.zeros_like(normalized, dtype=np.int32)
                labeled[12:20, 12:20] = 1
                labeled[26:34, 24:32] = 2
                return labeled, {}

        def fake_normalize(array, *args, **kwargs):
            return np.asarray(array, dtype=np.float32)

        with patch(
            "uchrom.im._pyhim._require_stardist",
            return_value=(DummyStarDist2D, None, fake_normalize, None),
        ), patch(
            "uchrom.im._pyhim.resolve_pyhim_model",
            return_value=("F:/models", "demo_mask2d"),
        ):
            result = segment(
                image,
                method="pyhim",
                background_method="stardist",
                tessellation=False,
                area_min=4,
                area_max=500,
            )

        self.assertEqual(result.meta["model_name"], "demo_mask2d")
        self.assertEqual(Path(result.meta["model_dir"]), Path("F:/models/demo_mask2d"))
        self.assertEqual(
            result.meta["label_semantics"],
            "filtered_instances_after_border_area_filter",
        )
        self.assertEqual(
            result.meta["raw_label_semantics"],
            "stardist_instances_before_border_area_filter",
        )
        self.assertIsNotNone(result.raw_labels)
        self.assertEqual(int(result.raw_labels.max()), 2)
        self.assertEqual(int(result.labels.max()), 2)

    def test_get_spot_properties_handles_sparse_nonconsecutive_labels(self):
        labels = np.zeros((4, 8, 8), dtype=np.int32)
        image = np.zeros_like(labels, dtype=float)
        labels[1, 2:4, 3:5] = 10000
        image[1, 2:4, 3:5] = 8.0
        labels[2, 5:7, 5:7] = 25000
        image[2, 5:7, 5:7] = 12.0

        spots, sharpness, roundness1, roundness2, npix, sky, peak, flux, mag = (
            get_spot_properties(labels, image, threshold=2.0, brightest=None)
        )

        self.assertEqual(spots.shape, (2, 3))
        np.testing.assert_array_equal(spots[:, 0], [1, 2])
        self.assertEqual(npix, [4, 4])
        self.assertEqual(peak, [8.0, 12.0])
        self.assertEqual(flux, [400.0, 600.0])
        self.assertTrue(all(value > 0 for value in sharpness))
        self.assertTrue(all(value > 0 for value in roundness1))
        self.assertTrue(all(value > 0 for value in roundness2))
        self.assertEqual(sky, [0.0, 0.0])
        self.assertEqual(len(mag), 2)

    def test_pyhim_3d_stardist_backend_keeps_stardist_labels(self):
        stack = np.ones((4, 16, 16), dtype=np.float32)

        class DummyStarDist3D:
            def __init__(self, *args, **kwargs):
                pass

            def _axes_div_by(self, axes):
                return (1, 1, 1)

            def predict_instances(self, normalized, n_tiles=None):
                labels = np.zeros_like(normalized, dtype=np.int32)
                labels[1:3, 4:8, 4:8] = 7
                labels[1:3, 8:12, 8:12] = 9
                return labels, {}

        def fake_normalize(array, *args, **kwargs):
            return np.asarray(array, dtype=np.float32)

        with patch(
            "uchrom.im._pyhim._require_stardist",
            return_value=(None, DummyStarDist3D, fake_normalize, None),
        ), patch(
            "uchrom.im._pyhim.resolve_pyhim_model",
            return_value=("F:/models", "demo_spots3d"),
        ):
            mask, labels = segment_spots_3d_stardist(stack)

        self.assertEqual(set(np.unique(labels)), {0, 7, 9})
        self.assertEqual(int(mask.max()), 1)


if __name__ == "__main__":
    unittest.main()
