"""Proxy / reference component — shares instances across the config tree."""

from experiment import ExperimentComponent, Param


class Ref(ExperimentComponent):
    """References a shared component by ID. Resolved by ExperimentBuilder."""
    component_type = "Ref"
    params = {"ref": Param(str, "", "ID of the component to reference")}
    def description(self): return f"ref -> {self.ref}"
