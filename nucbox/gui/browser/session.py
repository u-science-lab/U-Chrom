import json
from typing import Callable, Any, Dict, List

from nucbox.utils.io import read_particles


def _records_from_df(df):
    try:
        cols = [c for c in ['x', 'y', 'z', 'chrom', 'start', 'end'] if c in df.columns]
        if len(cols) == 0:
            return None
        return df[cols].to_dict('records')
    except Exception:
        return None


def _df_from_records(records):
    try:
        import pandas as pd
        if not isinstance(records, list):
            return None
        df = pd.DataFrame.from_records(records)
        for col in ["chrom", "x", "y", "z"]:
            if col not in df.columns:
                return None
        df["chrom"] = df["chrom"].astype(str)
        return df
    except Exception:
        return None


def export_window_session(win) -> Dict[str, Any]:
    canvases: List[Dict[str, Any]] = []
    for cv in win.get_all_canvas():
        cv_layers: List[Dict[str, Any]] = []
        try:
            for layer in getattr(cv.control_panel, 'layers', []):
                try:
                    entry: Dict[str, Any] = {
                        'type': 'Chromatin',
                        'name': getattr(layer, 'name', None),
                        'locked': getattr(layer, 'locked', False),
                    }
                    cache = getattr(layer, 'cache_props', {}) if hasattr(layer, 'cache_props') else {}
                    if isinstance(cache, dict):
                        entry['style'] = cache.get('style')
                        entry['width'] = cache.get('width')
                        entry['opacity'] = cache.get('opacity')
                        entry['color_mode'] = cache.get('color_mode')
                        entry['single_color'] = cache.get('single_color')
                        entry['chr_colormap'] = cache.get('chr_colormap', {})
                        entry['data_path'] = cache.get('data_path')
                        entry['props'] = {k: v for k, v in cache.items() if k in ['style', 'width', 'opacity', 'color_mode', 'single_color']}
                    df = getattr(layer, 'df', None)
                    if df is not None:
                        records = _records_from_df(df)
                        entry['df_records'] = records
                    cv_layers.append(entry)
                except Exception:
                    continue
        except Exception:
            pass

        try:
            dist = float(getattr(cv.view.camera, 'distance', 50.0))
        except Exception:
            dist = 50.0
        canvas_entry = {
            'layers': cv_layers,
            'camera': {
                'position': [0.0, 0.0, dist]
            },
            'axis_visible': bool(getattr(cv.axis, 'visible', False))
        }
        canvases.append(canvas_entry)

    data = {
        'version': 1,
        'chr_colormap': win.chr_colormap,
        'canvases': canvases
    }
    return data


def save_session_to_path(win, path: str) -> None:
    try:
        data = export_window_session(win)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(str(e))


def restore_window_from_session(win, data: Dict[str, Any]) -> None:
    try:
        if not isinstance(data, dict):
            print("Invalid session format: root is not an object")
            return

        canvases = data.get("canvases", [])
        if not isinstance(canvases, list):
            print("Invalid session format: 'canvases' is not a list")
            return

        for i, cv in enumerate(canvases):
            if i > 0:
                win.add_canvas('h')
            layers = []
            try:
                layers = cv.get("layers", []) if isinstance(cv, dict) else []
            except Exception:
                layers = []

            for layer_desc in layers:
                try:
                    if not isinstance(layer_desc, dict):
                        continue
                    layer_type = layer_desc.get("type")
                    if layer_type != "Chromatin":
                        continue
                    df = None
                    data_path = layer_desc.get("data_path")
                    if isinstance(data_path, str) and len(data_path) > 0:
                        try:
                            df = read_particles(data_path)
                        except Exception as e:
                            print(f"Failed to read data_path: {e}")
                    if df is None:
                        df_records = layer_desc.get("df_records")
                        df = _df_from_records(df_records)
                    if df is None:
                        continue

                    layer_colormap = layer_desc.get("chr_colormap")
                    if not isinstance(layer_colormap, dict):
                        layer_colormap = data.get("chr_colormap", {}) if isinstance(data.get("chr_colormap"), dict) else {}

                    width = layer_desc.get("width")
                    style = layer_desc.get("style")
                    name = layer_desc.get("name")
                    if not isinstance(width, (int, float)):
                        width = None
                    if not isinstance(style, str):
                        style = None

                    new_layer = win.canvas.control_panel.add_chromatin_layer(
                        df, layer_colormap, parent=None, name=name, width=width, style=style
                    )

                    props = layer_desc.get("props") if isinstance(layer_desc.get("props"), dict) else {}
                    color_mode = props.get("color_mode", layer_desc.get("color_mode"))
                    single_color = props.get("single_color", layer_desc.get("single_color"))
                    opacity = props.get("opacity", layer_desc.get("opacity"))

                    try:
                        if isinstance(color_mode, str):
                            new_layer.cache_props["color_mode"] = color_mode
                        if isinstance(single_color, str):
                            new_layer.cache_props["single_color"] = single_color
                        if isinstance(opacity, (int, float)):
                            new_layer.cache_props["opacity"] = float(opacity)
                        new_layer.cache_props["chr_colormap"] = layer_colormap
                        new_layer.remove()
                        new_layer.draw()
                    except Exception as e:
                        print(f"Failed to apply layer props: {e}")
                except Exception as e:
                    print(f"Failed to restore a layer: {e}")

            try:
                axis_vis = cv.get("axis_visible") if isinstance(cv, dict) else None
                if isinstance(axis_vis, bool):
                    win.canvas.axis.visible = axis_vis
            except Exception:
                pass

            try:
                cam = cv.get("camera") if isinstance(cv, dict) else None
                if isinstance(cam, dict):
                    pos = cam.get("position")
                    if isinstance(pos, list) and len(pos) == 3:
                        try:
                            import math
                            dist = math.sqrt(sum([float(pos[i])**2 for i in range(3)]))
                            win.canvas.view.camera.distance = dist
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception as e:
        print(str(e))


def load_session_from_path(path: str, create_window: Callable[[], Any]):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        win = create_window()
        restore_window_from_session(win, data)
        return win
    except Exception as e:
        print(str(e))
        return None


