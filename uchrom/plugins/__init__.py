"""
U-Chrom Plugin System

Allows users to extend U-Chrom with custom analysis and visualization plugins.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
import importlib.util
import sys
from pathlib import Path


class UChromPlugin(ABC):
    """
    Base class for U-Chrom plugins.

    Plugins can implement custom analysis and visualization methods.
    """

    def __init__(self):
        self.name = self.__class__.__name__
        self.version = "1.0.0"
        self.description = ""

    @abstractmethod
    def analyze(self, chromdata: Any, **kwargs) -> dict:
        """
        Perform custom analysis on ChromData.

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
        pass

    def visualize(self, result: dict, **kwargs) -> Optional[Any]:
        """
        Create custom visualization from analysis results.

        Parameters
        ----------
        result : dict
            Analysis results from analyze()
        **kwargs
            Additional parameters (style, dpi, etc.)

        Returns
        -------
        Figure or None
            Matplotlib figure or None if not implemented
        """
        return None

    def validate(self) -> bool:
        """
        Validate plugin configuration.

        Returns
        -------
        bool
            True if plugin is valid
        """
        return True


class PluginManager:
    """
    Manages plugin loading, registration, and execution.
    """

    def __init__(self):
        self.plugins: dict[str, UChromPlugin] = {}
        self.plugin_paths: list[Path] = []

    def register_plugin(self, plugin: UChromPlugin):
        """
        Register a plugin instance.

        Parameters
        ----------
        plugin : UChromPlugin
            Plugin instance to register
        """
        if not isinstance(plugin, UChromPlugin):
            raise TypeError(f"Plugin must inherit from UChromPlugin, got {type(plugin)}")

        if not plugin.validate():
            raise ValueError(f"Plugin {plugin.name} failed validation")

        self.plugins[plugin.name] = plugin
        print(f"Registered plugin: {plugin.name} v{plugin.version}")

    def load_plugin(self, path: str) -> UChromPlugin:
        """
        Load a plugin from a Python file.

        Parameters
        ----------
        path : str
            Path to plugin .py file

        Returns
        -------
        UChromPlugin
            Loaded plugin instance
        """
        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Plugin file not found: {path}")

        # Load module
        spec = importlib.util.spec_from_file_location(path_obj.stem, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load plugin: {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[path_obj.stem] = module
        spec.loader.exec_module(module)

        # Find plugin class
        plugin_class = None
        for name in dir(module):
            obj = getattr(module, name)
            if (isinstance(obj, type) and
                issubclass(obj, UChromPlugin) and
                obj is not UChromPlugin):
                plugin_class = obj
                break

        if plugin_class is None:
            raise ValueError(f"No UChromPlugin subclass found in {path}")

        # Instantiate and register
        plugin = plugin_class()
        self.register_plugin(plugin)
        return plugin

    def load_plugins_from_directory(self, directory: str):
        """
        Load all plugins from a directory.

        Parameters
        ----------
        directory : str
            Directory containing plugin .py files
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"Plugin directory not found: {directory}")

        for plugin_file in dir_path.glob("*.py"):
            if plugin_file.stem.startswith("_"):
                continue  # Skip private files
            try:
                self.load_plugin(str(plugin_file))
            except Exception as e:
                print(f"Failed to load plugin {plugin_file}: {e}")

    def get_plugin(self, name: str) -> Optional[UChromPlugin]:
        """
        Get a registered plugin by name.

        Parameters
        ----------
        name : str
            Plugin name

        Returns
        -------
        UChromPlugin or None
            Plugin instance or None if not found
        """
        return self.plugins.get(name)

    def list_plugins(self) -> list[dict]:
        """
        List all registered plugins.

        Returns
        -------
        list[dict]
            List of plugin metadata
        """
        return [
            {
                "name": plugin.name,
                "version": plugin.version,
                "description": plugin.description,
            }
            for plugin in self.plugins.values()
        ]

    def run_plugin(self, name: str, chromdata: Any, **kwargs) -> dict:
        """
        Run a plugin's analyze method.

        Parameters
        ----------
        name : str
            Plugin name
        chromdata : ChromData
            Input data
        **kwargs
            Additional parameters

        Returns
        -------
        dict
            Analysis results
        """
        plugin = self.get_plugin(name)
        if plugin is None:
            raise ValueError(f"Plugin not found: {name}")

        return plugin.analyze(chromdata, **kwargs)


# Global plugin manager instance
_plugin_manager = PluginManager()


def register_plugin(plugin: UChromPlugin):
    """Register a plugin with the global plugin manager."""
    _plugin_manager.register_plugin(plugin)


def load_plugin(path: str) -> UChromPlugin:
    """Load a plugin from a file."""
    return _plugin_manager.load_plugin(path)


def load_plugins_from_directory(directory: str):
    """Load all plugins from a directory."""
    _plugin_manager.load_plugins_from_directory(directory)


def get_plugin(name: str) -> Optional[UChromPlugin]:
    """Get a registered plugin by name."""
    return _plugin_manager.get_plugin(name)


def list_plugins() -> list[dict]:
    """List all registered plugins."""
    return _plugin_manager.list_plugins()


def run_plugin(name: str, chromdata: Any, **kwargs) -> dict:
    """Run a plugin's analyze method."""
    return _plugin_manager.run_plugin(name, chromdata, **kwargs)
