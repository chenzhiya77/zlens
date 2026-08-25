def test_package_imports_and_exposes_version():
    import zlens

    assert isinstance(zlens.__version__, str) and zlens.__version__
