"""韌體訊號與協定診斷套件 — 互動式教學導覽（Interactive Tutorial / Guided Walkthrough）。

提供 step-by-step 的互動教學引導，幫助工程師迅速掌握 I2C、SPI、UART 與板級拓撲
診斷工具的核心觀念與實戰操作。
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from fw_diag_tool.board_profile import SchemaError, load_board_profile
from fw_diag_tool.fault_arena.fixtures import FaultArenaFixtures
from fw_diag_tool.gui.shared import (
    analyze_i2c_input,
    analyze_spi_input,
    render_guide_expander,
    render_page_footer,
)
from fw_diag_tool.i2c.engine import I2CDiagnosticEngine
from fw_diag_tool.i2c.localization import localize_ack, localize_direction
from fw_diag_tool.i2c.models import I2CDirection
from fw_diag_tool.i2c.waveform import I2CWaveformReconstructor
from fw_diag_tool.resources import (
    load_i2c_sample,
    load_spi_sample,
)
from fw_diag_tool.uart.parser import UARTCrashParser

LEARNING_PATHS: dict[str, dict[str, Any]] = {
    "🟢 零基礎入門": {
        "desc": "從 I2C 基礎概念開始，逐步探索異常偵測、數位波形、SPI Flash、UART 崩潰與板卡拓撲。",
        "steps": [1, 2, 3, 4, 5, 6],
    },
    "🟡 已有硬體經驗": {
        "desc": "跳過基本 I2C 介紹，直接進入異常偵測、數位波形疊加、SPI 狀態機與 UART 堆疊分析。",
        "steps": [2, 3, 4, 5, 6],
    },
    "🔴 進階使用": {
        "desc": "專注於 SPI Flash 跨頁保護、UART Kernel Panic 堆疊解析與自訂 Board Profile 拓撲配置。",
        "steps": [4, 5, 6],
    },
}

TUTORIAL_STEPS: list[dict[str, Any]] = [
    {
        "id": 1,
        "title": "Step 1: 什麼是 I2C 協定？（I2C Protocol Basics）",
        "short_title": "1. I2C 基礎概念與交易解碼",
        "badge": "🟢 基礎入門",
        "summary": (
            "I2C 是韌體開發中最常見的雙線式同步序列通訊協定（SCL 時鐘線與 SDA 資料線）。"
            "透過 7-bit 位址尋址與 ACK/NACK 握手確認，主控端能與多個從屬裝置（如感測器、EEPROM）進行讀寫通訊。"
            "本步驟將示範如何載入 Saleae 邏輯分析儀解碼的 CSV 檔案，並自動解析交易序列。"
        ),
    },
    {
        "id": 2,
        "title": "Step 2: 認識 NACK 與異常偵測（Understanding NACK & Anomaly）",
        "short_title": "2. NACK 與異常根因診斷",
        "badge": "🟡 核心技能",
        "summary": (
            "在 I2C 傳輸中，若 Slave 晶片未將 SDA 拉低回應，即產生 NACK（No Acknowledge）。"
            "常見原因包含 Slave 未上電、位址錯誤、位址腳位（ADDR/A0/A1）浮接，或是 EEPROM 正處於內部寫入週期（tWR）忙碌狀態。"
            "診斷引擎會自動標記異常交易並提供排查指引與測試建議。"
        ),
    },
    {
        "id": 3,
        "title": "Step 3: 讀懂數位波形與時序圖（SCL / SDA Waveform Visualization）",
        "short_title": "3. SCL/SDA 數位波形與協定疊加",
        "badge": "🟡 核心技能",
        "summary": (
            "波形圖能直觀呈現 SCL 與 SDA 的轉態、START 條件、7-bit 位址傳輸、ACK/NACK 脈衝與 STOP 條件。"
            "透過顏色疊加（Overlay）標註，工程師能快速釐清每一位元組的語意與邊界，省去人工比對時序的繁瑣工作。"
        ),
    },
    {
        "id": 4,
        "title": "Step 4: SPI Flash 協定與狀態機（SPI NOR Flash Sequence）",
        "short_title": "4. SPI Flash 命令序列與狀態機",
        "badge": "🟡 核心技能",
        "summary": (
            "SPI NOR Flash 採用 CS、SCLK、MOSI、MISO 四線高速傳輸，遵循嚴格的狀態機命令序列。"
            "例如執行 Page Program（0x02）前必須先送出 Write Enable（WREN 0x06），且單次寫入不可跨越 256-byte 頁面邊界（Page Rollover）。"
            "本工具能自動驗證 JEDEC ID、命令合法性與跨頁覆蓋風險。"
        ),
    },
    {
        "id": 5,
        "title": "Step 5: UART 崩潰轉儲與堆疊解析（UART Crash Dump & HardFault）",
        "short_title": "5. UART 崩潰日誌與呼叫堆疊",
        "badge": "🔴 系統診斷",
        "summary": (
            "當嵌入式 Linux 發生 Kernel Panic 或 ARM Cortex-M 發生 HardFault 時，序列埠會輸出崩潰日誌與暫存器傾印。"
            "工具能自動擷取崩潰類型（如 NULL Pointer Dereference / Page Fault）、故障指令位址（RIP / PC）與 Call Trace 呼叫鏈，大幅加速根因定位。"
        ),
    },
    {
        "id": 6,
        "title": "Step 6: 進階：自訂 Board Profile 板卡拓撲（Custom Board Profile）",
        "short_title": "6. 自訂板卡拓撲與宣告比對",
        "badge": "🔴 進階拓撲",
        "summary": (
            "Board Profile 是描述硬體板卡 I2C 拓撲的 YAML 設定檔，定義匯流排編號、時鐘速率、MUX 切換與預期掛載的裝置清單。"
            "套用 Board Profile 後，診斷引擎能精準辨別未宣告的未知裝置、位址衝突與通道遺漏，是硬體 BSP 與驅動開發的最佳輔助工具。"
        ),
    },
]

DEFAULT_BOARD_PROFILE_YAML = """board_name: "demo-carrier-board"
version: "1.0"
i2c_buses:
  - bus_num: 0
    speed_mode: "standard"
    devices:
      - name: "eeprom_at24c02"
        address_7bit: 0x50
        category: "EEPROM"
        protocol: "I2C"
        compatible: "atmel,24c02"
        register_width: 8
      - name: "temp_lm75"
        address_7bit: 0x48
        category: "Temperature Sensor"
        protocol: "I2C"
        compatible: "national,lm75"
        register_width: 8
"""

DEFAULT_UART_PANIC_LOG = """BUG: unable to handle page fault for address: 0000000000000010
RIP: 0010:nvme_pci_complete_rq+0x38/0x120 [nvme]
RAX: 0000000000000000 RBX: ffff888102345000 RCX: 0000000000000000
CR2: 0000000000000010
Call Trace:
 <TASK>
 [ffff888100123450] blk_mq_complete_request+0x24/0x50
 [ffff8881001234a0] nvme_irq_handler+0x8c/0x100 [nvme]
 </TASK>"""


def _render_step_1_interactive() -> None:
    st.markdown("#### ▶️ 試試看：載入 I2C Decoded 範例並執行解碼")
    if st.button("載入並分析內建 I2C 範例", key="btn_run_step_1"):
        sample_csv = load_i2c_sample("builtin-decoded")
        rep, _ = analyze_i2c_input(sample_csv, "decoded_csv", 25.0)
        col1, col2, col3 = st.columns(3)
        col1.metric("總傳輸次數", f"{rep.total_transactions} 筆")
        col2.metric("識別裝置數", f"{len(rep.devices_detected)} 個")
        col3.metric("異常事件數", f"{len(rep.anomalies)} 項")

        rows = []
        for tx in rep.transactions[:6]:
            addr_str = f"0x{tx.address_7bit:02X}" if tx.address_available else "未知"
            dir_str = (
                localize_direction(tx.direction)
                if isinstance(tx.direction, I2CDirection)
                else str(tx.direction)
            )
            ack_str = localize_ack(tx.address_ack)
            data_hex = " ".join(f"0x{b:02X}" for b in tx.data_bytes[:4])
            if len(tx.data_bytes) > 4:
                data_hex += " …"
            rows.append(
                {
                    "交易 ID": f"Tx #{tx.id}",
                    "時間 (s)": f"{tx.start_time:.6f}",
                    "7-bit 位址": addr_str,
                    "讀寫方向": dir_str,
                    "ACK/NACK": ack_str,
                    "資料內容": data_hex or "無",
                }
            )
        st.dataframe(pd.DataFrame(rows))
        st.success("✅ 成功解析 I2C 交易序列！已識別 PMBus 電源模組與 24C02 EEPROM 裝置。")


def _render_step_2_interactive() -> None:
    st.markdown("#### ▶️ 試試看：載入含 NACK 異常範例並執行偵測")
    if st.button("載入並分析 NACK 異常範例", key="btn_run_step_2"):
        nack_csv = FaultArenaFixtures.get_case("01").builder()
        rep, _ = analyze_i2c_input(nack_csv, "decoded_csv", 25.0)
        if rep.anomalies:
            st.error(f"⚠️ 偵測到 {len(rep.anomalies)} 項協定異常！")
            for idx, issue in enumerate(rep.anomalies, start=1):
                with st.expander(f"異常 #{idx}：{issue.title}", expanded=True):
                    st.write(f"**詳細說明**：{issue.description}")
                    st.write(f"**根因推論**：\n{issue.root_cause_analysis}")
                    if issue.actionable_advice:
                        st.write("**建議排查動作**：")
                        for advice in issue.actionable_advice:
                            st.write(f"- {advice}")
        else:
            st.info("此追蹤記錄無異常。")


def _render_step_3_interactive() -> None:
    st.markdown("#### ▶️ 試試看：重建並繪製 I2C 數位波形圖")
    if st.button("繪製 SCL/SDA 數位波形圖", key="btn_run_step_3"):
        sample_csv = load_i2c_sample("builtin-decoded")
        engine = I2CDiagnosticEngine()
        report = engine.analyze_csv_content(sample_csv)
        tx = report.transactions[0]
        reconstructor = I2CWaveformReconstructor(default_clock_khz=100.0)
        wave_data = reconstructor.reconstruct_transaction_waveform(tx, max_points=20000)
        dir_text = "寫入" if tx.direction == I2CDirection.WRITE else "讀取"
        fig = I2CWaveformReconstructor.create_plotly_figure(
            wave_data,
            title=f"Tx #{tx.id} (位址 0x{tx.address_7bit:02X} {dir_text}) 數位波形與協定疊加",
        )
        st.plotly_chart(fig)
        st.caption(
            "💡 **波形顏色標記說明**：🟢 綠色=START 條件｜🔵 藍色=位址／資料位元｜"
            "🟢 青色=ACK 確認｜🔴 紅色=NACK｜🟣 紫色=STOP 條件"
        )


def _render_step_4_interactive() -> None:
    st.markdown("#### ▶️ 試試看：載入 SPI Flash 範例並執行協定解析")
    if st.button("載入並分析 SPI Flash 範例", key="btn_run_step_4"):
        spi_csv = load_spi_sample()
        rep = analyze_spi_input(spi_csv, max_page_size=256)
        col1, col2, col3 = st.columns(3)
        col1.metric("總傳輸次數", f"{rep.summary.total_transactions} 次")
        col2.metric("識別晶片型號", rep.summary.detected_flash_chip or "未知")
        col3.metric("寫入次數 (Page Program)", f"{rep.summary.write_count} 次")

        rows = []
        for tx in rep.transactions:
            rows.append(
                {
                    "序號": f"#{tx.index}",
                    "時間 (s)": f"{tx.start_time:.6f}",
                    "命令 Opcode": f"0x{tx.opcode:02X}" if tx.opcode is not None else "未知",
                    "指令名稱": tx.opcode_name,
                    "資料長度 (bytes)": tx.data_payload_len,
                    "解碼說明": tx.decoded_details or "—",
                }
            )
        st.dataframe(pd.DataFrame(rows))
        st.success("✅ 成功解析 SPI 命令序列！包含 0x9F (Read JEDEC ID) 與 0x02 (Page Program)。")


def _render_step_5_interactive() -> None:
    st.markdown("#### ▶️ 試試看：載入 Kernel Panic 崩潰記錄並執行解析")
    if st.button("解析 Linux Kernel Panic 日誌", key="btn_run_step_5"):
        rep = UARTCrashParser.parse_log_text(DEFAULT_UART_PANIC_LOG)
        if rep.kernel_panic is not None:
            kp = rep.kernel_panic
            st.error(f"💥 核心崩潰原因：{kp.panic_reason}")
            col1, col2 = st.columns(2)
            col1.write(f"**架構**：`{kp.architecture}`")
            col1.write(f"**故障位址 (CR2/Addr)**：`{kp.faulting_address}`")
            col2.write(f"**故障函式**：`{kp.faulting_func}`")
            col2.write(f"**故障指令 (RIP)**：`{kp.faulting_ip}`")

            if kp.call_trace:
                st.write("**呼叫堆疊（Call Trace）**：")
                for sym in kp.call_trace:
                    st.write(f"- `{sym}`")
            st.success(
                "✅ 成功提取當機暫存器與呼叫鏈！精確定位至 `nvme_pci_complete_rq` 空指標存取。"
            )


def _render_step_6_interactive() -> None:
    st.markdown("#### ▶️ 試試看：自訂 Board Profile 板卡拓撲並執行驗證")
    yaml_text = st.text_area(
        "編輯 Board Profile YAML 設定檔：",
        value=DEFAULT_BOARD_PROFILE_YAML,
        height=220,
        key="tutorial_board_profile_yaml",
    )
    if st.button("驗證與解析 Board Profile", key="btn_run_step_6"):
        try:
            profile = load_board_profile(yaml_text)
            st.success(
                f"✅ Board Profile 格式正確！板卡名稱：`{profile.board_name}` "
                f"（版本 {profile.version}）"
            )
            for bus in profile.i2c_buses:
                st.write(f"**I2C Bus {bus.bus_num}**（速度模式：`{bus.speed_mode}`）：")
                for dev in bus.devices:
                    st.write(
                        f"- **0x{dev.address_7bit:02X}**：`{dev.name}` "
                        f"（類別：{dev.category}，相容性：`{dev.compatible}`）"
                    )
        except SchemaError as exc:
            st.error(f"❌ Board Profile 格式錯誤：{exc}")


STEP_RENDERERS = {
    1: _render_step_1_interactive,
    2: _render_step_2_interactive,
    3: _render_step_3_interactive,
    4: _render_step_4_interactive,
    5: _render_step_5_interactive,
    6: _render_step_6_interactive,
}


def render() -> None:
    st.header("韌體訊號與協定診斷套件 — 互動式教學導覽（Interactive Walkthrough）")
    st.caption(
        "⚡ 專為韌體與嵌入式系統工程師打造的 step-by-step 互動式實戰教學，"
        "帶領你循序掌握各協定分析、異常診斷與除錯技巧。"
    )
    render_guide_expander(
        "chapters/ch01_i2c_diagnosis.md", "📖 點擊展開：I2C 診斷與通訊原理快速參考手冊"
    )

    if "tutorial_completed_steps" not in st.session_state:
        st.session_state["tutorial_completed_steps"] = set()
    completed_steps: set[int] = st.session_state["tutorial_completed_steps"]

    st.subheader("🎯 第一步：選擇適合你的學習路徑")
    selected_path = st.radio(
        "學習路徑選擇",
        list(LEARNING_PATHS.keys()),
        horizontal=True,
        key="tutorial_learning_path_radio",
    )
    path_info = LEARNING_PATHS[selected_path]
    st.info(f"**路徑說明**：{path_info['desc']}")

    path_step_ids: list[int] = path_info["steps"]
    completed_in_path = [s for s in path_step_ids if s in completed_steps]
    total_path_steps = len(path_step_ids)
    progress_ratio = len(completed_in_path) / total_path_steps if total_path_steps > 0 else 0.0

    st.subheader("📊 學習進度追蹤")
    st.progress(
        progress_ratio,
        text=f"路徑完成進度：{len(completed_in_path)} / {total_path_steps} 步驟 "
        f"({int(progress_ratio * 100)}%)",
    )

    col_reset, _col_jump = st.columns([1, 2])
    with col_reset:
        if st.button("🔄 重設本路徑進度", key="btn_reset_tutorial_progress"):
            for s in path_step_ids:
                completed_steps.discard(s)
            st.session_state["tutorial_completed_steps"] = completed_steps
            st.rerun()

    st.divider()

    for step in TUTORIAL_STEPS:
        step_id = step["id"]
        if step_id not in path_step_ids:
            continue

        is_done = step_id in completed_steps
        status_badge = "✅ 已完成" if is_done else "⏳ 待學習"

        with st.container(border=True):
            col_t1, col_t2 = st.columns([4, 1])
            col_t1.markdown(f"### {step['title']}")
            col_t2.markdown(f"**{status_badge}**\n`{step['badge']}`")

            st.write(step["summary"])

            # Interactive section
            renderer = STEP_RENDERERS.get(step_id)
            if renderer:
                renderer()

            # Completion toggle button
            if not is_done:
                if st.button("✅ 我理解了（標記完成此步驟）", key=f"btn_mark_done_{step_id}"):
                    completed_steps.add(step_id)
                    st.session_state["tutorial_completed_steps"] = completed_steps
                    st.rerun()
            else:
                if st.button("↩️ 取消完成標記", key=f"btn_unmark_done_{step_id}"):
                    completed_steps.discard(step_id)
                    st.session_state["tutorial_completed_steps"] = completed_steps
                    st.rerun()

    # All steps completed celebration
    if len(completed_in_path) == total_path_steps and total_path_steps > 0:
        st.divider()
        st.success("🎉 恭喜！你已完成此學習路徑的所有步驟！")
        st.balloons()
        st.markdown("### 🚀 接下來你可以前往實際功能模組進行深入分析：")
        c1, c2, c3 = st.columns(3)
        c1.info("📊 **I2C/PMBus 診斷**\n\n分析 Saleae 匯出檔與時鐘延展")
        c2.info("⚡ **SPI Flash 協定**\n\n檢查 NOR Flash 狀態機與跨頁覆蓋")
        c3.info("📟 **UART 崩潰轉儲**\n\n解析 ARM HardFault 與 Linux Panic")

    render_page_footer()


__all__ = ["render"]
