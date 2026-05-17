"""
Example Plugin: Structure Compactness

Measures chromatin structure compactness using radius of gyration.
"""

from uchrom.plugins import UChromPlugin
import numpy as np


class CompactnessPlugin(UChromPlugin):
    """
    Measure chromatin structure compactness.

    Computes radius of gyration, asphericity, and other shape descriptors.
    """

    def __init__(self):
        super().__init__()
        self.name = "Compactness"
        self.version = "1.0.0"
        self.description = "Measure structure compactness and shape"

    def analyze(self, chromdata, **kwargs):
        """
        Compute compactness metrics.

        Parameters
        ----------
        chromdata : ChromData
            Input chromatin structure data

        Returns
        -------
        dict
            Compactness metrics
        """
        coords = chromdata.coords

        # Center of mass
        center = np.mean(coords, axis=0)

        # Radius of gyration
        rg = np.sqrt(np.mean(np.sum((coords - center) ** 2, axis=1)))

        # Moment of inertia tensor
        I = np.zeros((3, 3))
        for i in range(3):
            for j in range(3):
                I[i, j] = np.sum((coords[:, i] - center[i]) * (coords[:, j] - center[j]))
        I /= len(coords)

        # Eigenvalues (principal moments)
        eigenvalues = np.linalg.eigvalsh(I)
        eigenvalues = np.sort(eigenvalues)[::-1]  # Descending order

        # Asphericity
        asphericity = eigenvalues[0] - 0.5 * (eigenvalues[1] + eigenvalues[2])

        # Acylindricity
        acylindricity = eigenvalues[1] - eigenvalues[2]

        # Shape anisotropy
        shape_anisotropy = (
            (eigenvalues[0] - eigenvalues[1]) ** 2
            + (eigenvalues[1] - eigenvalues[2]) ** 2
            + (eigenvalues[2] - eigenvalues[0]) ** 2
        ) / (2 * (eigenvalues[0] + eigenvalues[1] + eigenvalues[2]) ** 2)

        # Bounding box
        bbox_min = np.min(coords, axis=0)
        bbox_max = np.max(coords, axis=0)
        bbox_size = bbox_max - bbox_min

        return {
            "radius_of_gyration": float(rg),
            "center_of_mass": center.tolist(),
            "principal_moments": eigenvalues.tolist(),
            "asphericity": float(asphericity),
            "acylindricity": float(acylindricity),
            "shape_anisotropy": float(shape_anisotropy),
            "bounding_box": {
                "min": bbox_min.tolist(),
                "max": bbox_max.tolist(),
                "size": bbox_size.tolist(),
            },
        }

    def visualize(self, result, **kwargs):
        """
        Visualize compactness metrics.

        Parameters
        ----------
        result : dict
            Analysis results from analyze()

        Returns
        -------
        Figure
            Matplotlib figure
        """
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        # Plot 1: Principal moments
        ax = axes[0]
        moments = result["principal_moments"]
        ax.bar(["λ1", "λ2", "λ3"], moments, color=["#89b4fa", "#a6e3a1", "#f38ba8"])
        ax.set_ylabel("Principal Moment")
        ax.set_title("Principal Moments of Inertia")
        ax.grid(alpha=0.3)

        # Plot 2: Shape metrics
        ax = axes[1]
        metrics = {
            "Rg": result["radius_of_gyration"],
            "Asphericity": result["asphericity"],
            "Acylindricity": result["acylindricity"],
            "Anisotropy": result["shape_anisotropy"],
        }
        ax.barh(list(metrics.keys()), list(metrics.values()), color="#89b4fa")
        ax.set_xlabel("Value")
        ax.set_title("Shape Descriptors")
        ax.grid(alpha=0.3)

        plt.tight_layout()
        return fig
