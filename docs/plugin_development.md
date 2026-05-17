# U-Chrom Plugin Development Guide

## Overview

U-Chrom's plugin system allows you to extend the platform with custom analysis and visualization methods. Plugins are Python modules that inherit from `UChromPlugin` and implement the `analyze()` method.

## Quick Start

### 1. Create a Plugin

```python
from uchrom.plugins import UChromPlugin
import numpy as np

class MyPlugin(UChromPlugin):
    def __init__(self):
        super().__init__()
        self.name = "MyPlugin"
        self.version = "1.0.0"
        self.description = "My custom analysis"

    def analyze(self, chromdata, **kwargs):
        """
        Perform custom analysis.
        
        Parameters
        ----------
        chromdata : ChromData
            Input chromatin structure data
        **kwargs
            Additional parameters
            
        Returns
        -------
        dict
            Analysis results
        """
        coords = chromdata.coords
        
        # Your analysis here
        result = {
            "n_points": len(coords),
            "mean_x": float(np.mean(coords[:, 0])),
            "mean_y": float(np.mean(coords[:, 1])),
            "mean_z": float(np.mean(coords[:, 2])),
        }
        
        return result

    def visualize(self, result, **kwargs):
        """
        Optional: Create visualization.
        
        Parameters
        ----------
        result : dict
            Analysis results from analyze()
            
        Returns
        -------
        Figure or None
            Matplotlib figure
        """
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots()
        ax.bar(["X", "Y", "Z"], [result["mean_x"], result["mean_y"], result["mean_z"]])
        ax.set_ylabel("Mean Coordinate")
        ax.set_title("Mean Position")
        
        return fig
```

### 2. Load and Use Plugin

```python
from uchrom.plugins import load_plugin, run_plugin
from uchrom.core import ChromData

# Load plugin
plugin = load_plugin("my_plugin.py")

# Load data
cd = ChromData.read("data.h5cd")

# Run analysis
result = run_plugin("MyPlugin", cd)
print(result)

# Visualize
fig = plugin.visualize(result)
fig.savefig("result.png")
```

## Plugin API Reference

### UChromPlugin Base Class

All plugins must inherit from `UChromPlugin` and implement the `analyze()` method.

#### Required Methods

**`analyze(chromdata, **kwargs) -> dict`**

Perform custom analysis on ChromData.

- **Parameters**:
  - `chromdata` (ChromData): Input chromatin structure data
  - `**kwargs`: Additional parameters
- **Returns**: dict with analysis results

#### Optional Methods

**`visualize(result, **kwargs) -> Figure | None`**

Create custom visualization from analysis results.

- **Parameters**:
  - `result` (dict): Analysis results from `analyze()`
  - `**kwargs`: Additional parameters (style, dpi, etc.)
- **Returns**: Matplotlib Figure or None

**`validate() -> bool`**

Validate plugin configuration.

- **Returns**: True if plugin is valid

### Plugin Manager

The `PluginManager` class handles plugin loading and execution.

#### Functions

**`register_plugin(plugin: UChromPlugin)`**

Register a plugin instance.

**`load_plugin(path: str) -> UChromPlugin`**

Load a plugin from a Python file.

**`load_plugins_from_directory(directory: str)`**

Load all plugins from a directory.

**`get_plugin(name: str) -> UChromPlugin | None`**

Get a registered plugin by name.

**`list_plugins() -> list[dict]`**

List all registered plugins.

**`run_plugin(name: str, chromdata, **kwargs) -> dict`**

Run a plugin's analyze method.

## Example Plugins

### 1. Distance Statistics

Computes pairwise distance statistics.

```python
from uchrom.plugins.examples.distance_stats import DistanceStatsPlugin

plugin = DistanceStatsPlugin()
result = plugin.analyze(chromdata)
# Returns: mean, median, std, min, max, histogram
```

### 2. Structure Compactness

Measures chromatin structure compactness using radius of gyration.

```python
from uchrom.plugins.examples.compactness import CompactnessPlugin

plugin = CompactnessPlugin()
result = plugin.analyze(chromdata)
# Returns: radius_of_gyration, asphericity, principal_moments, etc.
```

### 3. Data Export

Export chromatin structure data to various formats.

```python
from uchrom.plugins.examples.data_export import DataExportPlugin

plugin = DataExportPlugin()
result = plugin.analyze(chromdata, format="pdb")
# Returns: PDB format data
```

## Best Practices

### 1. Error Handling

Always handle errors gracefully:

```python
def analyze(self, chromdata, **kwargs):
    try:
        # Your analysis
        pass
    except Exception as e:
        return {"error": str(e)}
```

### 2. Input Validation

Validate inputs before processing:

```python
def analyze(self, chromdata, **kwargs):
    if chromdata.coords is None or len(chromdata.coords) == 0:
        raise ValueError("No coordinates in ChromData")
    
    # Continue with analysis
```

### 3. Return Structured Data

Always return JSON-serializable dictionaries:

```python
def analyze(self, chromdata, **kwargs):
    result = {
        "metric1": float(value1),  # Convert numpy types
        "metric2": int(value2),
        "data": array.tolist(),    # Convert arrays to lists
    }
    return result
```

### 4. Documentation

Document your plugin thoroughly:

```python
class MyPlugin(UChromPlugin):
    """
    Brief description of what the plugin does.
    
    Detailed explanation of the analysis method,
    expected inputs, and outputs.
    """
    
    def analyze(self, chromdata, **kwargs):
        """
        Detailed docstring for analyze method.
        
        Parameters
        ----------
        chromdata : ChromData
            Description
        param1 : type
            Description
            
        Returns
        -------
        dict
            Description of return value structure
        """
        pass
```

## Web API Integration

Plugins can be used via the web API:

### List Plugins

```bash
GET /api/plugins
```

Response:
```json
{
  "plugins": [
    {
      "name": "DistanceStats",
      "version": "1.0.0",
      "description": "Compute pairwise distance statistics"
    }
  ]
}
```

### Load Plugin

```bash
POST /api/plugins/load
Content-Type: multipart/form-data

file: my_plugin.py
```

### Run Plugin

```bash
POST /api/plugins/run?plugin_name=MyPlugin&session_id=abc123
```

Response:
```json
{
  "success": true,
  "result": {
    "metric1": 123.45,
    "metric2": 67
  }
}
```

## Advanced Topics

### Accessing ChromData Attributes

```python
def analyze(self, chromdata, **kwargs):
    # Coordinates
    coords = chromdata.coords  # (n_spots, 3) array
    
    # Genomic positions
    spots = chromdata.spots  # DataFrame with chrom, start, end
    
    # Cell metadata
    if chromdata.cells is not None:
        cells = chromdata.cells  # DataFrame
    
    # Tracks (epigenomic signals)
    if chromdata.tracks is not None:
        tracks = chromdata.tracks  # DataFrame
```

### Using External Libraries

Plugins can use any Python library:

```python
from uchrom.plugins import UChromPlugin
from sklearn.decomposition import PCA
import networkx as nx

class NetworkPlugin(UChromPlugin):
    def analyze(self, chromdata, **kwargs):
        # Use scikit-learn
        pca = PCA(n_components=2)
        reduced = pca.fit_transform(chromdata.coords)
        
        # Use networkx
        G = nx.Graph()
        # Build graph...
        
        return {"pca": reduced.tolist(), "graph": nx.node_link_data(G)}
```

### Stateful Plugins

Plugins can maintain state:

```python
class StatefulPlugin(UChromPlugin):
    def __init__(self):
        super().__init__()
        self.cache = {}
    
    def analyze(self, chromdata, use_cache=True, **kwargs):
        key = id(chromdata)
        if use_cache and key in self.cache:
            return self.cache[key]
        
        result = self._compute(chromdata)
        self.cache[key] = result
        return result
```

## Troubleshooting

### Plugin Not Loading

- Check that your plugin file has a class that inherits from `UChromPlugin`
- Ensure the file is valid Python syntax
- Check for import errors in your plugin

### Analysis Fails

- Validate input data before processing
- Add try-except blocks for error handling
- Return error information in the result dict

### Visualization Not Showing

- Ensure `visualize()` returns a matplotlib Figure
- Check that all required libraries are installed
- Test visualization separately before integrating

## Contributing Plugins

To contribute your plugin to the U-Chrom plugin repository:

1. Create a pull request with your plugin in `uchrom/plugins/contrib/`
2. Include documentation and examples
3. Add tests in `tests/test_plugins.py`
4. Follow the code style guidelines

## License

Plugins inherit the U-Chrom license unless otherwise specified.
