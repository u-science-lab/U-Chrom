import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from uchrom.im import z_project, z_project_dir


class TestZProject(unittest.TestCase):
    def test_z_project_mip_whole_stack_from_array_is_float64(self):
        stack = np.arange(3 * 4 * 5).reshape(3, 4, 5)
        result = z_project(stack, method="mip", save=False)
        expected = np.max(stack, axis=0).astype(np.float64)

        self.assertEqual(result.dtype, np.float64)
        np.testing.assert_array_equal(result, expected)

    def test_z_project_sum_with_z_range_from_array_is_float64(self):
        stack = np.arange(5 * 3 * 4).reshape(5, 3, 4)
        result = z_project(stack, method="sum", zmin=1, zmax=4, save=False)
        expected = np.sum(stack[1:4], axis=0).astype(np.float64)

        self.assertEqual(result.dtype, np.float64)
        np.testing.assert_array_equal(result, expected)

    def test_invalid_stack_dimension_raises(self):
        arr = np.ones((4, 4))
        with self.assertRaises(ValueError):
            z_project(arr, save=False)

    def test_invalid_method_raises(self):
        stack = np.ones((3, 4, 4))
        with self.assertRaises(ValueError):
            z_project(stack, method="mean", save=False)

    def test_invalid_z_range_raises(self):
        stack = np.ones((3, 4, 4))
        with self.assertRaises(ValueError):
            z_project(stack, zmin=2, zmax=2, save=False)
        with self.assertRaises(ValueError):
            z_project(stack, zmin=-1, zmax=2, save=False)
        with self.assertRaises(ValueError):
            z_project(stack, zmin=0, zmax=4, save=False)

    def test_permission_error_propagates(self):
        stack = np.ones((3, 4, 4))
        with mock.patch(
            "uchrom.im.prep.project._ensure_writable_dir",
            side_effect=PermissionError("not writable"),
        ):
            with self.assertRaises(PermissionError):
                z_project(stack, save=True)

    def test_tiff_input_save_outputs_npy_is_float64(self):
        stack = np.arange(4 * 6 * 7, dtype=np.uint16).reshape(4, 6, 7)
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input"
            input_dir.mkdir()
            tif_path = input_dir / "stack.tif"
            tif_path.touch()

            with mock.patch(
                "uchrom.im.prep.project._read_stack",
                return_value=stack,
            ):
                result = z_project(tif_path, method="mip", save=True)

            expected = np.max(stack, axis=0).astype(np.float64)
            np.testing.assert_array_equal(result, expected)
            self.assertEqual(result.dtype, np.float64)

            out_root = Path(tmpdir) / "project"
            npy_path = out_root / "data" / "stack_2d.npy"
            png_path = out_root / "preview" / "stack_2d.png"

            self.assertTrue(npy_path.exists())
            self.assertTrue(png_path.exists())
            saved = np.load(npy_path)
            self.assertEqual(saved.dtype, np.float64)
            np.testing.assert_array_equal(saved, expected)

    def test_tiff_input_save_false_does_not_write(self):
        stack = np.arange(4 * 5 * 6, dtype=np.uint16).reshape(4, 5, 6)
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input"
            input_dir.mkdir()
            tif_path = input_dir / "stack.tiff"
            tif_path.touch()

            with mock.patch(
                "uchrom.im.prep.project._read_stack",
                return_value=stack,
            ):
                result = z_project(tif_path, method="sum", save=False)

            expected = np.sum(stack, axis=0).astype(np.float64)
            np.testing.assert_array_equal(result, expected)
            self.assertEqual(result.dtype, np.float64)
            self.assertFalse((Path(tmpdir) / "project").exists())

    def test_directory_batch_outputs_npy_is_float64(self):
        stack1 = np.arange(3 * 4 * 5, dtype=np.uint16).reshape(3, 4, 5)
        stack2 = (np.arange(3 * 4 * 5, dtype=np.uint16).reshape(3, 4, 5) + 1)
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input"
            input_dir.mkdir()
            (input_dir / "a.tif").touch()
            (input_dir / "b.tiff").touch()

            def fake_read_stack(path):
                if Path(path).suffix.lower() == ".tif":
                    return stack1
                return stack2

            with mock.patch(
                "uchrom.im.prep.project._read_stack",
                side_effect=fake_read_stack,
            ):
                records = z_project_dir(input_dir, method="mip")

            self.assertEqual(len(records), 2)
            out_root = Path(tmpdir) / "project"
            a_npy = out_root / "data" / "a_2d.npy"
            b_npy = out_root / "data" / "b_2d.npy"

            self.assertTrue(a_npy.exists())
            self.assertTrue(b_npy.exists())
            self.assertEqual(np.load(a_npy).dtype, np.float64)
            self.assertEqual(np.load(b_npy).dtype, np.float64)

    def test_directory_without_tiff_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                z_project_dir(tmpdir)


if __name__ == "__main__":
    unittest.main()
