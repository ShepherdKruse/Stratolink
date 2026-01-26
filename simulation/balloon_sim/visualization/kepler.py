"""
Kepler.gl visualization for balloon trajectories.

Creates interactive HTML visualizations using Kepler.gl.
"""

from typing import Optional, Union
import json

try:
    from keplergl import KeplerGl
    HAS_KEPLER = True
except Exception as e:
    # print the error
    print(e)
    HAS_KEPLER = False

from balloon_sim.fleet import Fleet
from balloon_sim.balloon import Balloon


def _check_kepler():
    """Raise error if keplergl is not installed."""
    if not HAS_KEPLER:
        raise ImportError(
            "keplergl is required for this visualization. "
            "Install with: pip install keplergl"
        )


def create_kepler_trajectory_map(
    fleet_or_balloon: Union[Fleet, Balloon],
    map_height: int = 800,
    animate: bool = True,
    trail_length: float = 1.0,
    color_by_balloon: bool = True,
) -> "KeplerGl":
    """
    Create an interactive Kepler.gl map with balloon trajectories.

    Args:
        fleet_or_balloon: Fleet or single Balloon to visualize
        map_height: Height of the map in pixels
        animate: Whether to enable animation (trip layer)
        trail_length: Trail length for animation (0-1, fraction of total time)
        color_by_balloon: Color trajectories by balloon ID

    Returns:
        KeplerGl map object
    """
    _check_kepler()

    # Get balloons
    if isinstance(fleet_or_balloon, Balloon):
        balloons = [fleet_or_balloon]
    else:
        balloons = fleet_or_balloon.balloons

    if animate:
        # Use trip layer for animation - requires specific format
        data = _create_trip_data(balloons)
        config = _create_trip_config(len(balloons), trail_length, color_by_balloon)
    else:
        # Use line layer for static view
        data = _create_line_data(balloons)
        config = _create_line_config(len(balloons), color_by_balloon)

    # Create map
    map_obj = KeplerGl(height=map_height, data={"trajectories": data}, config=config)

    return map_obj


def _create_trip_data(balloons: list) -> dict:
    """Create GeoJSON data for trip layer animation."""
    features = []

    for balloon in balloons:
        # Trip layer expects coordinates as [lon, lat, altitude, timestamp]
        # We use hour index as timestamp (Kepler interprets as unix timestamp)
        coordinates = []
        for i, (lat, lon) in enumerate(zip(balloon.lats, balloon.lons)):
            # Kepler expects [lon, lat, altitude, timestamp]
            # Use hour * 3600 to convert to "seconds" for smoother animation
            coordinates.append([lon, lat, 0, i * 3600])

        feature = {
            "type": "Feature",
            "properties": {
                "balloon_id": balloon.balloon_id,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
        }
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}


def _create_line_data(balloons: list) -> dict:
    """Create GeoJSON data for static line layer."""
    features = []

    for balloon in balloons:
        coordinates = [[lon, lat] for lat, lon in zip(balloon.lats, balloon.lons)]

        feature = {
            "type": "Feature",
            "properties": {
                "balloon_id": balloon.balloon_id,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
        }
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}


def _create_trip_config(n_balloons: int, trail_length: float, color_by_balloon: bool) -> dict:
    """Create Kepler.gl config for animated trip layer."""
    # Color palette for balloons
    colors = [
        [255, 99, 71],    # tomato
        [30, 144, 255],   # dodger blue
        [50, 205, 50],    # lime green
        [255, 215, 0],    # gold
        [238, 130, 238],  # violet
        [0, 206, 209],    # dark turquoise
        [255, 165, 0],    # orange
        [147, 112, 219],  # medium purple
        [60, 179, 113],   # medium sea green
        [255, 105, 180],  # hot pink
    ]

    return {
        "version": "v1",
        "config": {
            "visState": {
                "filters": [],
                "layers": [
                    {
                        "id": "trip_layer",
                        "type": "trip",
                        "config": {
                            "dataId": "trajectories",
                            "label": "Balloon Trajectories",
                            "color": [255, 99, 71],
                            "columns": {
                                "geojson": "_geojson",
                            },
                            "isVisible": True,
                            "visConfig": {
                                "opacity": 0.8,
                                "thickness": 2,
                                "colorRange": {
                                    "name": "Custom",
                                    "type": "custom",
                                    "category": "Custom",
                                    "colors": [
                                        "#FF6347", "#1E90FF", "#32CD32", "#FFD700",
                                        "#EE82EE", "#00CED1", "#FFA500", "#9370DB",
                                        "#3CB371", "#FF69B4"
                                    ][:n_balloons],
                                },
                                "trailLength": trail_length,
                                "fadeTrail": True,
                            },
                            "colorField": {
                                "name": "balloon_id",
                                "type": "string",
                            } if color_by_balloon else None,
                        },
                        "visualChannels": {
                            "colorField": {
                                "name": "balloon_id",
                                "type": "string",
                            } if color_by_balloon else None,
                            "colorScale": "ordinal" if color_by_balloon else None,
                        },
                    }
                ],
                "animationConfig": {
                    "currentTime": None,
                    "speed": 1,
                },
            },
            "mapState": {
                "bearing": 0,
                "latitude": 35,
                "longitude": -95,
                "pitch": 0,
                "zoom": 3,
            },
            "mapStyle": {
                "styleType": "muted",
            },
        },
    }


def _create_line_config(n_balloons: int, color_by_balloon: bool) -> dict:
    """Create Kepler.gl config for static line layer."""
    return {
        "version": "v1",
        "config": {
            "visState": {
                "filters": [],
                "layers": [
                    {
                        "id": "line_layer",
                        "type": "geojson",
                        "config": {
                            "dataId": "trajectories",
                            "label": "Balloon Trajectories",
                            "color": [255, 99, 71],
                            "columns": {
                                "geojson": "_geojson",
                            },
                            "isVisible": True,
                            "visConfig": {
                                "opacity": 0.8,
                                "thickness": 1.5,
                                "colorRange": {
                                    "name": "Custom",
                                    "type": "custom",
                                    "category": "Custom",
                                    "colors": [
                                        "#FF6347", "#1E90FF", "#32CD32", "#FFD700",
                                        "#EE82EE", "#00CED1", "#FFA500", "#9370DB",
                                        "#3CB371", "#FF69B4"
                                    ][:n_balloons],
                                },
                                "filled": False,
                                "stroked": True,
                            },
                            "colorField": {
                                "name": "balloon_id",
                                "type": "string",
                            } if color_by_balloon else None,
                        },
                        "visualChannels": {
                            "colorField": {
                                "name": "balloon_id",
                                "type": "string",
                            } if color_by_balloon else None,
                            "colorScale": "ordinal" if color_by_balloon else None,
                        },
                    }
                ],
            },
            "mapState": {
                "bearing": 0,
                "latitude": 35,
                "longitude": -95,
                "pitch": 0,
                "zoom": 3,
            },
            "mapStyle": {
                "styleType": "muted",
            },
        },
    }


def export_kepler_html(
    fleet_or_balloon: Union[Fleet, Balloon],
    output_path: str,
    map_height: int = 800,
    animate: bool = True,
    trail_length: float = 1.0,
    color_by_balloon: bool = True,
    read_only: bool = False,
) -> str:
    """
    Export balloon trajectories to an interactive HTML file.

    Args:
        fleet_or_balloon: Fleet or single Balloon to visualize
        output_path: Path to save the HTML file
        map_height: Height of the map in pixels
        animate: Whether to enable animation (trip layer)
        trail_length: Trail length for animation (0-1, fraction of total time)
        color_by_balloon: Color trajectories by balloon ID
        read_only: If True, hide the side panel for a cleaner view

    Returns:
        Path to the saved HTML file
    """
    _check_kepler()

    map_obj = create_kepler_trajectory_map(
        fleet_or_balloon,
        map_height=map_height,
        animate=animate,
        trail_length=trail_length,
        color_by_balloon=color_by_balloon,
    )

    map_obj.save_to_html(file_name=output_path, read_only=read_only)
    print(f"Saved Kepler.gl visualization to {output_path}")

    return output_path
