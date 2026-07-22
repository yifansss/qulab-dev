def test_live_models_and_optional_qt_import_safe():
    import qulab.gui.live_data_catalog  # noqa: F401
    import qulab.gui.live_plot_model  # noqa: F401
    import qulab.gui.analysis_status_model  # noqa: F401
    import qulab.gui.sequence_context_model  # noqa: F401
    import qulab.gui.pyqt_views  # noqa: F401
