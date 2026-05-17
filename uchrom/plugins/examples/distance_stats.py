"""
Example Plugin: Distance Statistics

Computes pairwise distance statistics for chromatin structure.
"""

from uchrom.plugins import UChromPlugin
import numpy as np
from scipy.spatial.distance import pdist, squareform


class DistanceStatsPlugin(UChromPlugin):
    """
    Compute distance statistics for chromatin structure.

    Calculates mean, median, std, min, max distances between genomic bins.
    """

    def __init__(self):
        super().__init__()
        self.name = "DistanceStats"
        self.version = "1.0.0"
        self.description = "Compute pairwise distance statistics"

    def analyze(self, chromdata, **kwargs):
        """
        Compute distance statistics.

        Parameters
        ----------
        chromdata : ChromData
            Input chromatin structure data

        Returns
        -------
        dict
            Distance statistics
        """
        coords = chromdata.coords

        # Compute pairwise distances
        distances = pdist(coords)

        # Statistics
        stats = {
            "mean": float(np.mean(distances)),
            "median": float(np.median(distances)),
            "std": float(np.std(distances)),
            "min": float(np.min(distances)),
            "max": float(np.max(distances)),
            "n_points": len(coords),
            "n_pairs": len(distances),
        }

        # Distance distribution (histogram)
        hist, bin_edges = np.histogram(distances, bins=50)
        stats["histogram"] = {
            "counts": hist.tolist(),
            "bin_edges": bin_edges.tolist(),
        }

        return stats

    def visualize(self, result, **kwargs):
        """
        Visualize distance distribution.

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

        fig, ax = plt.subplots(figsize=(8, 5))

        # Plot histogram
        hist_data = result["histogram"]
        bin_centers = [
            (hist_data["bin_edges"][i] + hist_data["bin_edges"][i + 1]) / 2
            for i in range(len(hist_data["counts"]))
        ]
        ax.bar(bin_centers, hist_data["counts"], width=bin_centers[1] - bin_centers[0], alpha=0.7)

        # Add mean line
        ax.axvline(result["mean"], color="red", linestyle="--", label=f"Mean: {result['mean']:.2f}")

        ax.set_xlabel("Distance (nm)")
        ax.set_ylabel("Count")
        ax.set_title("Pairwise Distance Distribution")
        ax.legend()
        ax.grid(alpha=0.3)

        return fig
