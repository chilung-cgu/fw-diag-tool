from pathlib import Path

from fw_diag_tool.analyzers.register_mapper import RegisterMapCatalog


def test_gui_app_syntax():
    app_path = Path("src/fw_diag_tool/gui/app.py")
    assert app_path.exists()
    code = app_path.read_text(encoding="utf-8")
    assert "st.set_page_config" in code
    assert "I2CDiagnosticEngine" in code
    assert "PCIeAnalyzer" in code
    assert "if csv_text is not None:" in code


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
