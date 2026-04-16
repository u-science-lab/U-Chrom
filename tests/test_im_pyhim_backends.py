import unittest

import numpy as np

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
        stack = np.zeros((9, 32, 32), dtype=float)
        stack[3:6, 10:14, 12:16] = 20.0
        stack[4:7, 20:24, 20:24] = 18.0
        stack[2:5, 5:8, 5:8] = 10.0

        result = localize(
            {"RT26": stack},
            method="pyhim_3d",
            backend="thresholding",
            reduce_planes=False,
            threshold_over_std=5.0,
            area_min=2,
            area_max=500,
            brightest=100,
            subpixel_refine=False,
            z_binning=2,
        )

        self.assertFalse(result.table.empty)
        self.assertTrue({"Barcode #", "zcentroid", "xcentroid", "ycentroid"}.issubset(result.table.columns))
        self.assertTrue((result.table["Barcode #"] == 26).all())


if __name__ == "__main__":
    unittest.main()
