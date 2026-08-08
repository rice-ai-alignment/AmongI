"""Position modes — how agents move through the world."""

from experiment import ExperimentComponent, Param


class TilePosition(ExperimentComponent):
    """Discrete 2D tile-based movement."""
    component_type = "Position"
    params = {"map": Param(None, None, "Map component defining walkable tiles")}
    exposes = {
        "functions": {
            "distance_between": {
                "args": ["id_a", "id_b"],
                "returns": "float",
                "desc": "Euclidean distance between two entities by ID",
            },
            "get_position": {
                "args": ["id"],
                "returns": "Tile",
                "desc": "Get the tile position of an entity by ID",
            },
        },
    }
    def __init__(self, map=None, **kwargs):
        super().__init__(**kwargs)
        self.map = map
    def description(self): return "tile-based grid movement"
