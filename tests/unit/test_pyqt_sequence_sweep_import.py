def test_pyqt_sequence_sweep_import_safe():
    import qulab.gui.sequence_sweep_model
    import qulab.gui.pyqt_views

    assert qulab.gui.sequence_sweep_model.SequenceSweepEditorModel is not None
