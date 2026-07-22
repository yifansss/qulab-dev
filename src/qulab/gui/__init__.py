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
from .live_data_catalog import LiveDataCatalog, LiveDataKeySpec, LivePointBuffer
from .live_plot_model import LivePlotModel, LivePlotSelection
from .analysis_status_model import AnalysisStatusModel, ModuleStatus
from .sequence_context_model import SequenceContext, SequenceContextModel

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
    "LiveDataCatalog", "LiveDataKeySpec", "LivePointBuffer", "LivePlotModel", "LivePlotSelection",
    "AnalysisStatusModel", "ModuleStatus", "SequenceContext", "SequenceContextModel",
]
