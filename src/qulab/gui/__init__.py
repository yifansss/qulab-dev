"""Graphical experiment control interface."""
"""Operator GUI package.

Importing this package does not create a GUI window. Use
``python -m qulab.gui.operator_app`` to launch the Tkinter MVP console.
"""

from .controller import OperatorController
from .models import ParameterEdit, PreflightViewModel, ResourceViewModel, RunViewModel
from .plot_model import PlotSeries
from .procedure_tree import ProcedureTreeNode, build_procedure_tree
from .workflow_model import WorkflowNode, build_workflow_tree

__all__ = [
    "OperatorController",
    "ParameterEdit",
    "PlotSeries",
    "PreflightViewModel",
    "ProcedureTreeNode",
    "ResourceViewModel",
    "RunViewModel",
    "WorkflowNode",
    "build_procedure_tree",
    "build_workflow_tree",
]
