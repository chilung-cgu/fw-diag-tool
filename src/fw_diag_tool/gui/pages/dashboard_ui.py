from __future__ import annotations

import importlib.metadata
import platform
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from fw_diag_tool import __version__
from fw_diag_tool.gui.shared import _FAULT_ARENA_CASES_ZH, render_page_footer
from fw_diag_tool.gui.theme import get_plotly_template
from fw_diag_tool.i18n import t
from fw_diag_tool.metrics import get_metrics_collector
from fw_diag_tool.session.session_manager import SessionManager


def _get_example_data_count() -> int:
    """掃描 examples/data/ 目錄內的範例檔案數量。"""
    try:
        repo_root = Path(__file__).resolve().parents[4]
        data_dir = repo_root / "examples" / "data"
        if not data_dir.exists():
            data_dir = Path("examples/data")
        if data_dir.is_dir():
            return len([f for f in data_dir.iterdir() if f.is_file()])
    except (OSError, ValueError):
        return 17
    return 17


def _render_quick_link(url_path: str, label: str) -> None:
    """嘗試使用 st.page_link 呈現快速啟動按鈕，若不支援則降級至 markdown 連結。"""
    try:
        st.page_link(url_path, label=label, use_container_width=True)
    except Exception:
        st.markdown(f"[{label}]({url_path})")


def _render_quick_actions() -> None:
    with st.expander("⚡ 快速操作", expanded=False):
        actions = (
            ("i2c-diagnosis", "📊 I2C 診斷"),
            ("spi", "⚡ SPI Flash"),
            ("pcie", "🚀 PCIe AER"),
            ("fault-arena", "🏆 Fault Arena"),
        )
        columns = st.columns(4)
        for column, (url_path, label) in zip(columns, actions):
            with column:
                _render_quick_link(url_path, label)


def _render_system_info() -> None:
    st.subheader("📋 系統資訊")
    metrics = (
        ("Python 版本", platform.python_version()),
        ("工具版本", f"v{__version__}"),
        ("頁面數", "26"),
        ("協定數", "5"),
    )
    columns = st.columns(4)
    for column, (label, value) in zip(columns, metrics):
        with column:
            st.metric(label=label, value=value)


def _check_dependency(name: str) -> tuple[bool, str]:
    """Check if a Python package is importable and return (ok, version)."""
    try:
        version = importlib.metadata.version(name)
        return True, version
    except importlib.metadata.PackageNotFoundError:
        return False, "未安裝"


def _render_environment_health() -> None:
    """呈現環境健康看板，以 metric 卡片顯示關鍵依賴版本與 Python 環境健康狀態。"""
    st.subheader("🏥 環境健康看板")
    py_ver = platform.python_version()
    py_parts = tuple(int(x) for x in py_ver.split(".")[:2])
    py_ok = py_parts >= (3, 10)

    key_deps = (
        ("streamlit", "Streamlit"),
        ("plotly", "Plotly"),
        ("pandas", "Pandas"),
        ("pydantic", "Pydantic"),
        ("rich", "Rich"),
    )

    columns = st.columns(6)
    with columns[0]:
        st.metric(
            label="Python",
            value=py_ver,
            delta="✅ >= 3.10" if py_ok else "⚠️ < 3.10",
        )
    for column, (dep_pkg, dep_name) in zip(columns[1:], key_deps):
        ok, ver = _check_dependency(dep_pkg)
        with column:
            st.metric(
                label=dep_name,
                value=ver if ok else "未安裝",
                delta="✅ 正常" if ok else "⚠️ 未安裝",
            )


def _render_health_check() -> None:
    """Render system health check panel in an expander."""
    with st.expander("🏥 系統健康檢查", expanded=False):
        py_ver = platform.python_version()
        py_parts = tuple(int(x) for x in py_ver.split(".")[:2])
        py_ok = py_parts >= (3, 10)

        st.markdown("**Python 環境**")
        if py_ok:
            st.markdown(f"✅ Python {py_ver} (>= 3.10 ✓)")
        else:
            st.markdown(f"❌ Python {py_ver} (需要 >= 3.10)")

        st.markdown("**核心套件**")
        core_deps = ["streamlit", "plotly", "pandas", "pydantic", "rich", "typer", "pyyaml"]
        all_core_ok = True
        for dep in core_deps:
            ok, ver = _check_dependency(dep)
            if not ok:
                all_core_ok = False
            icon = "✅" if ok else "❌"
            st.markdown(f"{icon} {dep}: {ver}")

        st.markdown("**可選套件**")
        optional_deps = [("fpdf2", "PDF 報告匯出"), ("hypothesis", "模糊測試")]
        for dep, purpose in optional_deps:
            ok, ver = _check_dependency(dep)
            icon = "✅" if ok else "⚠️"
            st.markdown(f"{icon} {dep} ({purpose}): {ver}")

        st.markdown("**範例資料**")
        example_count = _get_example_data_count()
        icon = "✅" if example_count > 0 else "⚠️"
        st.markdown(f"{icon} 內建範例檔案：{example_count} 個")

        st.divider()
        if py_ok and all_core_ok:
            st.success("系統健康：所有核心檢查通過 ✓")
        elif py_ok:
            st.warning("系統部分健康：部分核心套件缺失")
        else:
            st.error("系統異常：Python 版本或核心套件不符合要求")


def _render_quick_import() -> None:
    """呈現快速匯入入口，支援一鍵載入最近一次 Session 檔案並繼續分析。"""
    with st.expander("⚡ 快速匯入最近 Session", expanded=False):
        try:
            manager = SessionManager()
            sessions = manager.list_sessions() if hasattr(manager, "list_sessions") else []
        except Exception:
            sessions = []

        if not sessions:
            st.info("尚無已儲存的 Session 檔案。請在各協定診斷頁面執行分析並點擊「儲存 Session」。")
            return

        latest = sessions[0]
        latest_path = latest.get("path")
        latest_name = latest.get("name") or latest.get("filename") or "未命名"
        latest_time = latest.get("created_at", "未知時間")
        latest_filename = latest.get("filename", "")

        st.markdown(
            f"**最近一次 Session**：`{latest_name}`（建立時間：`{latest_time}`）  \n"
            f"**檔案名稱**：`{latest_filename}`"
        )

        load_btn = st.button("🚀 一鍵載入最近 Session", key="btn_quick_import_latest")

        if load_btn:
            if not latest_path:
                st.error("無法取得最近 Session 檔案路徑。")
                return
            try:
                doc = manager.load_document(latest_path)
                if hasattr(st, "session_state"):
                    st.session_state["dashboard_quick_imported_session"] = doc
                st.success(f"✅ 成功載入 Session「{doc.name or latest_name}」！")

                with st.container(border=True):
                    st.markdown(f"##### 📋 Session 內容摘要：{doc.name or latest_name}")
                    meta_c1, meta_c2, meta_c3 = st.columns(3)
                    with meta_c1:
                        st.metric("工具版本", doc.tool_version)
                    with meta_c2:
                        st.metric("建立時間", doc.created_at or "—")
                    with meta_c3:
                        report_keys_count = len(doc.report) if isinstance(doc.report, dict) else 0
                        st.metric("報告欄位數", str(report_keys_count))

                    if doc.notes:
                        st.markdown(f"**備註**：{doc.notes}")

                    st.markdown("**可進行的下一步操作**：")
                    nav_c1, nav_c2, nav_c3 = st.columns(3)
                    with nav_c1:
                        _render_quick_link("session-compare", "⚖️ 前往 Session 比對")
                    with nav_c2:
                        _render_quick_link("session-analytics", "📈 前往 Session 趨勢分析")
                    with nav_c3:
                        _render_quick_link("i2c-diagnosis", "📊 前往 I2C 診斷")
            except Exception as exc:
                st.error(f"❌ 載入 Session 失敗：{exc}")


def _render_recent_sessions() -> None:
    """Render a recent analysis sessions panel."""
    with st.expander("📂 最近分析記錄", expanded=False):
        try:
            manager = SessionManager()
            sessions = manager.list_sessions() if hasattr(manager, "list_sessions") else []
            if not sessions:
                st.info("尚無已儲存的分析記錄。請在各協定分析頁面使用「儲存 Session」功能。")
                return
            # Show at most 10 recent sessions
            recent = sessions[:10]
            rows = []
            for s in recent:
                if isinstance(s, dict):
                    name = s.get("name") or (str(s["session_id"])[:8] if "session_id" in s else "—")
                    protocol = s.get("protocol", "—")
                    created_at = s.get("created_at", "—")
                else:
                    name = getattr(
                        s, "name", str(s.session_id)[:8] if hasattr(s, "session_id") else "—"
                    )
                    protocol = getattr(s, "protocol", "—")
                    created_at = getattr(s, "created_at", "—")
                rows.append(
                    {
                        "名稱": name,
                        "協定": protocol,
                        "建立時間": created_at,
                    }
                )
            if rows:
                import pandas as pd

                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        except Exception:
            st.caption("無法載入最近記錄。")


def _render_analysis_history() -> None:
    """呈現各協定分析次數歷史統計圖表。"""
    st.subheader("📈 分析歷史統計")
    collector = get_metrics_collector()
    summary = collector.get_summary()
    protocol_usage = summary.get("protocol_usage", {})

    default_protocols = ["I2C", "SPI", "UART", "PCIe", "MCTP"]
    chart_data = {proto: protocol_usage.get(proto, 0) for proto in default_protocols}
    for proto, count in protocol_usage.items():
        if proto not in chart_data:
            chart_data[proto] = count

    has_data = any(v > 0 for v in chart_data.values())

    fig = go.Figure(
        go.Bar(
            x=list(chart_data.keys()),
            y=list(chart_data.values()),
            name="協定分析次數",
            marker_color="#2563eb",
            text=list(chart_data.values()),
            textposition="auto",
        )
    )
    fig.update_layout(
        template=get_plotly_template(),
        title="各協定使用頻率與分析次數",
        xaxis_title="協定 (Protocol)",
        yaxis_title="分析次數 (Count)",
        height=320,
        margin=dict(l=40, r=40, t=50, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)
    if not has_data:
        st.caption("ℹ️ 目前尚無協定分析記錄。在各協定診斷頁面執行分析時將自動記錄並更新。")


def _render_usage_metrics() -> None:
    collector = get_metrics_collector()
    summary = collector.get_summary()

    with st.expander("📊 本次使用統計", expanded=False):
        page_usage = summary["page_usage"]
        if page_usage:
            fig = go.Figure(
                go.Bar(x=list(page_usage.keys()), y=list(page_usage.values()), name="Page usage")
            )
            fig.update_layout(
                template=get_plotly_template(),
                title="各頁面使用次數",
                xaxis_title="頁面",
                yaxis_title="次數",
                height=320,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("尚未記錄使用事件。")

        recent_events = collector.get_recent_events(10)
        if recent_events:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "時間": event.timestamp,
                            "頁面": event.page_name,
                            "動作": event.action,
                            "協定": event.protocol or "",
                            "耗時 (ms)": event.duration_ms,
                        }
                        for event in recent_events
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("最近事件：無")

        st.download_button(
            "下載使用統計 CSV",
            data=collector.export_csv(),
            file_name="fw_diag_usage_metrics.csv",
            mime="text/csv",
            key="dashboard_usage_metrics_csv",
        )


def render() -> None:
    st.header(t("title_dashboard", domain="gui"))
    st.caption(
        f"⚡ fw-diag-tool v{__version__} — 專為韌體與嵌入式系統工程師打造的離線訊號、協定與崩潰轉儲診斷分析套件。"
    )

    _render_quick_actions()
    _render_system_info()
    _render_environment_health()
    _render_health_check()

    # 系統狀態面板
    st.subheader(t("system_dashboard", domain="gui"))
    stat_col1, stat_col2, stat_col3 = st.columns(3)
    with stat_col1:
        st.metric(
            label=t("tool_version_runtime", domain="gui"),
            value=f"v{__version__}",
            delta=f"Python {platform.python_version()}",
            delta_color="off",
        )
    with stat_col2:
        st.metric(
            label=t("installed_modules_protocols", domain="gui"),
            value="26 Pages",
            delta="6 大協定 (I2C, SPI, UART, PCIe, MCTP, DTS)",
            delta_color="off",
        )
    with stat_col3:
        fault_arena_count = len(_FAULT_ARENA_CASES_ZH)
        example_count = _get_example_data_count()
        st.metric(
            label=t("scenarios_example_files", domain="gui"),
            value=f"{fault_arena_count} Scenarios",
            delta=f"{example_count} 個內建範例檔",
            delta_color="off",
        )

    # 快速啟動按鈕
    st.markdown(f"#### {t('quick_launch', domain='gui')}")
    qcols = st.columns(6)
    with qcols[0]:
        _render_quick_link("i2c-diagnosis", t("quick_link_i2c", domain="gui"))
    with qcols[1]:
        _render_quick_link("waveform-diff", t("quick_link_diff", domain="gui"))
    with qcols[2]:
        _render_quick_link("pcie", t("quick_link_pcie", domain="gui"))
    with qcols[3]:
        _render_quick_link("uart", t("quick_link_uart", domain="gui"))
    with qcols[4]:
        _render_quick_link("spi", t("quick_link_spi", domain="gui"))
    with qcols[5]:
        _render_quick_link("fault-arena", t("quick_link_fault_arena", domain="gui"))

    _render_quick_import()

    st.divider()

    st.info(
        "💡 **工具能力邊界聲明**：\n"
        "- 本工具主要分析已擷取的追蹤記錄（Trace）、日誌（Log）與暫存器傾印（Dump），不會主動連線或控制實體硬體。\n"
        "- 圖表與診斷報告能有效縮小除錯範圍，但無法取代示波器實體量測、晶片規格書（Datasheet）及目標板上的實體驗證。"
    )

    with st.expander("🚀 第一次使用？快速入門指引與場景導覽", expanded=False):
        st.markdown(
            "### 3 步快速上手流程\n\n"
            "1. **準備擷取資料**：從邏輯分析儀（如 Saleae）、串列埠終端（如 minicom/picocom）或系統日誌（dmesg/lspci）匯出 CSV、TXT 或十六進位資料。\n"
            "2. **切換至對應功能頁面**：於左側導覽列選擇目標協定（如 I2C/PMBus、SPI、PCIe、UART）或代碼產生工具。\n"
            "3. **載入資料並檢視報告**：可直接上傳檔案、貼上文字，或點擊「載入範例」體驗自動化診斷分析與下載 Markdown 報告。\n\n"
            "---"
        )
        st.markdown(
            "### 常見工作場景推薦起始頁面\n\n"
            "- **I2C / PMBus 匯流排通訊失敗、NACK、時鐘延展或死鎖**：推薦 **📊 I2C/PMBus 診斷** 或 **⚖️ 雙波形差分**。\n"
            "- **系統當機、Linux Kernel Panic 或 ARM HardFault**：推薦 **📟 UART Crash**。\n"
            "- **伺服器 BMC / IPMI / PLDM 封包分析與 Checksum 驗證**：推薦 **🌐 MCTP/IPMB**。\n"
            "- **PCIe 裝置無法識別、Link 降速或 AER 錯誤回報**：推薦 **🚀 PCIe AER**。\n"
            "- **Flash 讀寫異常、WREN 遺漏或 256B 跨頁覆蓋**：推薦 **⚡ SPI Flash**。\n"
            "- **撰寫 Linux 裝置樹、解析狀態暫存器或產生 C 驅動巨集**：推薦 **🌲 Device Tree**、**🎛 暫存器解碼** 或 **🛠 C Header 產生器**。\n"
            "- **新人培訓、故障模式排查練習或建立除錯心智模型**：推薦 **🏆 Fault Arena** 與 **📚 除錯 SOP**。"
        )

    st.subheader(t("module_overview", domain="gui"))

    st.markdown(f"#### {t('nav_category_protocols', domain='gui')}")
    col1, col2, col3 = st.columns(3)
    with col1, st.container(border=True):
        st.markdown("##### 📊 I2C/PMBus 診斷")
        st.write("**說明**：解碼 CSV/raw trace，分析 timing、anomaly、chip 識別")
        st.write(
            "**支援格式**：Saleae Decoded CSV、Raw Digital CSV (100 kHz / 400 kHz)、Text Trace、.fwsession.json"
        )
        st.write(
            "**適用場景**：I2C/SMBus/PMBus 通訊失敗、NACK、時鐘延展 (Clock Stretching) 逾時、匯流排死鎖 (Bus Hang)、電源晶片狀態分析"
        )
    with col2, st.container(border=True):
        st.markdown("##### 🎨 I2C 封包模擬器")
        st.write("**說明**：自訂 I2C 傳輸規格，產生波形與 C driver code")
        st.write("**支援格式**：自訂 7-bit 位址、暫存器位移、讀寫長度、寫入資料 Payload")
        st.write(
            "**適用場景**：驅動開發前的封包行為模擬、i2ctransfer CLI 命令生成、Linux Kernel i2c_msg / C driver 程式碼範本"
        )
    with col3, st.container(border=True):
        st.markdown("##### ⚖️ 雙波形差分")
        st.write("**說明**：Golden vs Failing trace 比對")
        st.write("**支援格式**：兩個 Saleae Decoded CSV（正常板卡 Golden vs 故障板卡 Failing）")
        st.write(
            "**適用場景**：板卡 A/B 對比除錯、找出首次通訊分歧點（Timing Jitter、位址/資料 NACK 差異、長度不符）"
        )

    st.markdown(f"#### {t('nav_category_system', domain='gui')}")
    col4, col5, col6, col7 = st.columns(4)
    with col4, st.container(border=True):
        st.markdown("##### 📟 UART Crash")
        st.write("**說明**：Linux kernel panic / ARM HardFault crash dump 解析")
        st.write(
            "**支援格式**：文字日誌 (.txt / .log)、Linux dmesg / Call Trace、ARM Cortex-M 暫存器轉儲 (HFSR/CFSR/Stacked PC)"
        )
        st.write(
            "**適用場景**：Linux 核心當機 (Kernel Panic / Oops / NULL Pointer)、ARM 微控制器 HardFault (除以零、未對齊存取、非精確匯流排錯誤)"
        )
    with col5, st.container(border=True):
        st.markdown("##### 🌐 MCTP/IPMB")
        st.write("**說明**：伺服器管理協定封包解碼")
        st.write("**支援格式**：十六進位位元組字串 (Hex Bytes，以空白、逗號或分號分隔)")
        st.write(
            "**適用場景**：BMC 伺服器管理協定除錯、MCTP (DSP0236 / PLDM / SPDM) 封包解碼與順序驗證、IPMB (IPMI v2.0) 兩段 Checksum 校驗"
        )
    with col6, st.container(border=True):
        st.markdown("##### 🚀 PCIe AER")
        st.write("**說明**：PCIe config space 與進階錯誤報告")
        st.write(
            "**支援格式**：lspci -xxxx / -vvv 十六進位傾印、Linux dmesg AER 錯誤記錄、自訂 64+ bytes Hex Dump"
        )
        st.write(
            "**適用場景**：PCIe 裝置無法識別、Link 降速 (Gen4 -> Gen1)、進階錯誤回報 (AER Correctable/Uncorrectable/Fatal)、Malformed/Poisoned TLP 診斷"
        )
    with col7, st.container(border=True):
        st.markdown("##### ⚡ SPI Flash")
        st.write("**說明**：SPI NOR Flash 命令序列與異常偵測")
        st.write("**支援格式**：邏輯分析儀 SPI Decoded CSV (需含 timestamp, MOSI, MISO, CS/Enable)")
        st.write(
            "**適用場景**：SPI NOR Flash 讀寫異常、JEDEC ID 全 0xFF/0x00 排查、Page Program 遺漏 WREN (0x06)、Page Buffer (256B) 跨頁回繞覆蓋偵測"
        )

    st.markdown(f"#### {t('nav_category_tools', domain='gui')}")
    col8, col9, col10 = st.columns(3)
    with col8, st.container(border=True):
        st.markdown("##### 🌲 Device Tree")
        st.write("**說明**：從拓撲定義產生 .dts/.dtsi")
        st.write("**支援格式**：YAML 格式的 I2C / MUX 匯流排與周邊裝置拓撲定義")
        st.write(
            "**適用場景**：Linux 系統移植與板級支援包 (BSP) 開發、自動產生標準 OpenBMC / Linux I2C Device Tree 節點"
        )
    with col9, st.container(border=True):
        st.markdown("##### 🎛 暫存器解碼")
        st.write("**說明**：Bitfield 解碼器支援自訂 YAML")
        st.write(
            "**支援格式**：十六進位暫存器數值 (如 0x18000)、內建/自訂 YAML 暫存器對映檔 (Register Map)"
        )
        st.write(
            "**適用場景**：硬體狀態暫存器欄位即時拆解、PMBus STATUS_WORD / PCIe AER 錯誤暫存器 bitfield 快速查閱"
        )
    with col10, st.container(border=True):
        st.markdown("##### 🛠 C Header 產生器")
        st.write("**說明**：暫存器定義轉 C macro")
        st.write("**支援格式**：YAML 暫存器與欄位定義檔")
        st.write(
            "**適用場景**：韌體/驅動開發中將暫存器定義自動轉換為符合規範的 C 語言 #define 位移、遮罩與讀改寫 (RMW) 巨集"
        )

    st.markdown(f"#### {t('nav_category_labs', domain='gui')}")
    col11, col12 = st.columns(2)
    with col11, st.container(border=True):
        st.markdown("##### 🏆 Fault Arena")
        st.write("**說明**：20 個合成除錯案例")
        st.write("**支援格式**：內建 20 個經典案例一鍵載入（涵蓋 I2C、SPI、PCIe、UART、MCTP/IPMB）")
        st.write(
            "**適用場景**：初階工程師除錯實戰培訓、各類硬韌體故障模式（NACK, Timeout, Rollover, HardFault 等）演練與自動診斷比對"
        )
    with col12, st.container(border=True):
        st.markdown("##### 📚 除錯 SOP")
        st.write("**說明**：L1-L7 分層診斷模型")
        st.write("**支援格式**：互動式知識庫與對照手冊（無須輸入）")
        st.write(
            "**適用場景**：建立系統化除錯心智模型、依據 L1 (物理) 到 L7 (應用) 分層定位問題邊界、判斷各層所需量測工具與證據"
        )

    st.markdown("---")
    st.subheader(t("whats_new_title", domain="gui"))
    with st.expander(t("whats_new_expander", domain="gui"), expanded=True):
        st.markdown(
            "- **📟 CLI 差分對稱完善**：新增 `pcie diff` 與 `mctp diff` 子命令，五大協定均支援 CLI 差分對比。\n"
            "- **🔗 跨協定時間線擴展**：Correlation UI 從 3 協定擴展至 5 協定 (I2C/SPI/UART/PCIe/MCTP)。\n"
            "- **💾 Session 儲存對稱補齊**：SPI、UART、PCIe、MCTP 頁面新增「儲存分析 Session」功能。\n"
            "- **📄 Diff JSON 匯出**：五大協定 Diff 結果支援 JSON 結構化報告下載。\n"
            "- **🌍 i18n 完整性稽核**：補齊 40+ 缺少的翻譯詞條，新增 AST 自動化檢查測試。\n"
            "- **📊 Dashboard 強化**：環境健康看板、分析歷史統計圖表、快速 Session 匯入。\n"
            "- **📖 README 全面更新**：26 頁 GUI 功能矩陣表、完整 CLI 指令速查。"
        )

    _render_analysis_history()
    _render_recent_sessions()
    _render_usage_metrics()
    render_page_footer()


__all__ = ["render"]
