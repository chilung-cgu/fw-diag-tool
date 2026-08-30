from pathlib import Path

from fw_diag_tool.analyzers.register_mapper import RegisterMapCatalog


def test_gui_app_syntax():
    app_path = Path("src/fw_diag_tool/gui/app.py")
    assert app_path.exists()
    code = app_path.read_text(encoding="utf-8")
    assert "st.set_page_config" in code
    assert "st.navigation" in code
    assert "i2c_diagnosis" in code
    assert "pcie_ui" in code
    assert "inject_custom_theme" in code


def test_gui_theme_and_config():
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

    from fw_diag_tool.gui.theme import inject_custom_theme, render_metric_card

    config_path = Path(".streamlit/config.toml")
    assert config_path.exists()

    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert config["theme"]["primaryColor"] == "#0ea5e9"
    assert config["theme"]["backgroundColor"] == "#0f172a"
    assert config["theme"]["secondaryBackgroundColor"] == "#1e293b"
    assert config["theme"]["textColor"] == "#e2e8f0"
    assert config["server"]["headless"] is True
    assert config["browser"]["gatherUsageStats"] is False

    # Test callable without uncaught runtime exception
    inject_custom_theme()
    render_metric_card(label="測試", value="100", delta="+1", help_text="說明")


def test_builtin_register_yamls():
    data_dir = Path("src/fw_diag_tool/data")
    assert (data_dir / "pmbus_standard.yaml").exists()
    assert (data_dir / "pcie_aer_registers.yaml").exists()

    cat = RegisterMapCatalog()
    cat.load_from_yaml((data_dir / "pmbus_standard.yaml").read_text(encoding="utf-8"))
    assert "status_word" in cat.name_map

    cat_pcie = RegisterMapCatalog()
    cat_pcie.load_from_yaml((data_dir / "pcie_aer_registers.yaml").read_text(encoding="utf-8"))
    assert "uncorrectable_error_status" in cat_pcie.name_map
