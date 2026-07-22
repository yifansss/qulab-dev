def test_pyqt_sequence_sweep_import_safe():
    import qulab.gui.sequence_sweep_model
    import qulab.gui.pyqt_views

    assert qulab.gui.sequence_sweep_model.SequenceSweepEditorModel is not None


def test_generic_fixed_transform_parameters_use_visible_sweep_table():
    from qulab.gui.sequence_authoring_view import parameter_table_for_mode

    assert parameter_table_for_mode("generic", "fixed") == "sweep"
    assert parameter_table_for_mode("generic", "linspace") == "sweep"
    assert parameter_table_for_mode("curated", "fixed") == "fixed"
