from __future__ import annotations

import re

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .models import ServerMgmtReport

_SUMMARY_RE = re.compile(
    r"^Decoded (\d+) MCTP packet\(s\) and (\d+) IPMB frame\(s\)\."
    r"(?: (\d+) input line\(s\) were not decoded\.)?$"
)
_INCOMPLETE_TOKEN_RE = re.compile(r"^line (\d+): incomplete byte token (.+)$")
_UNRECOGNIZED_LINE_RE = re.compile(r"^line (\d+): no recognizable MCTP packet or IPMB frame$")
_SEQUENCE_MISMATCH_RE = re.compile(r"^sequence mismatch: expected (\d+), got (\d+)$")
_PLDM_INFO_RE = re.compile(
    r"^PLDM (?P<type>.+) (?P<direction>Request|Response): Cmd (?P<cmd>0x[0-9A-Fa-f]+) "
    r"\(Instance (?P<instance>\d+)\)(?: \[CC: (?P<cc>0x[0-9A-Fa-f]+)\])?$"
)
_MCTP_PACKET_SUMMARY_RE = re.compile(
    r"^MCTP: EID (?P<src>0x[0-9A-Fa-f]+) -> (?P<dest>0x[0-9A-Fa-f]+) "
    r"\[(?P<type>.+?)\] Tag:(?P<tag>0x[0-9A-Fa-f]+)(?: \((?P<pldm>PLDM .+)\))?$"
)
_MCTP_MESSAGE_SUMMARY_RE = re.compile(
    r"^MCTP Message: EID (?P<src>0x[0-9A-Fa-f]+) -> (?P<dest>0x[0-9A-Fa-f]+) "
    r"\[(?P<type>.+?)\] \((?P<packets>\d+) pkts, (?P<bytes>\d+) bytes\)"
    r"(?: \((?P<pldm>PLDM .+)\))?(?: \[Error: (?P<error>.+)\])?$"
)
_MCTP_ORPHAN_SUMMARY_RE = re.compile(
    r"^MCTP: Orphan packet without SOM \(Tag: (?P<tag>0x[0-9A-Fa-f]+)\)$"
)
_MCTP_INCOMPLETE_SUMMARY_RE = re.compile(
    r"^MCTP: Incomplete message from EID (?P<src>0x[0-9A-Fa-f]+) \(missing EOM\)$"
)

_MCTP_TYPE_ZH = {
    "MCTP Control Message": "MCTP 控制訊息",
    "PLDM": "PLDM（平台層資料模型）",
    "NC-SI over MCTP": "MCTP 上的 NC-SI",
    "Ethernet over MCTP": "MCTP 上的 Ethernet",
    "NVMe-MI over MCTP": "MCTP 上的 NVMe-MI",
    "SPDM": "SPDM（安全通訊協定與資料模型）",
    "VDPCI": "VDPCI（廠商自訂 PCI）",
    "VDIANA": "VDIANA（廠商自訂 IANA）",
    "Continuation Segment": "延續片段",
    "Orphan Continuation": "孤立延續片段",
}
_PLDM_TYPE_ZH = {
    "Base": "基礎（Base）",
    "SMBIOS": "SMBIOS",
    "Platform Monitoring & Control (Sensors)": "平台監控與控制（感測器）",
    "BIOS Control & Configuration": "BIOS 控制與設定",
    "FRU Data": "FRU 資料",
    "Firmware Update (DSP0267)": "韌體更新（DSP0267）",
    "Redfish Device Enablement": "Redfish 裝置啟用",
}
_IPMB_NETFN_ZH = {
    "Chassis": "機箱（Chassis）",
    "Bridge": "橋接（Bridge）",
    "Sensor / Event": "感測器／事件（Sensor / Event）",
    "App": "應用（App）",
    "Firmware": "韌體（Firmware）",
    "Storage": "儲存（Storage）",
    "Group Extension": "群組延伸（Group Extension）",
    "OEM / Board Management": "OEM／板級管理（OEM / Board Management）",
}
_IPMB_COMMAND_ZH = {
    "Get Device ID": "取得裝置識別碼（Get Device ID）",
    "Cold Reset": "冷重設（Cold Reset）",
    "Get Self Test Results": "取得自我測試結果（Get Self Test Results）",
    "Set Event Receiver": "設定事件接收器（Set Event Receiver）",
    "Get Sensor Reading": "取得感測器讀值（Get Sensor Reading）",
    "Get Sensor Reading Factors": "取得感測器讀值因子（Get Sensor Reading Factors）",
    "Get FRU Inventory Area Info": "取得 FRU 清單區資訊（Get FRU Inventory Area Info）",
    "Read FRU Data": "讀取 FRU 資料（Read FRU Data）",
    "Write FRU Data": "寫入 FRU 資料（Write FRU Data）",
}


def _localize_named_token(value: str, translations: dict[str, str]) -> str:
    """Translate the descriptive prefix and retain a canonical source token."""
    for source, target in translations.items():
        if value == source:
            return target
        if value.startswith(source + " ("):
            suffix = value[len(source) + 2 : -1]
            if suffix in {"Request", "Response"}:
                direction = "請求（Request）" if suffix == "Request" else "回應（Response）"
                return f"{target} {direction}"
            if target.endswith("）"):
                return f"{target[:-1]}；{suffix}）"
            return f"{target}（{suffix}）"
    return value


def _localize_msg_type(value: str) -> str:
    return _localize_named_token(value, _MCTP_TYPE_ZH)


def _localize_pldm_type(value: str) -> str:
    return _localize_named_token(value, _PLDM_TYPE_ZH)


def _localize_netfn(value: str) -> str:
    return _localize_named_token(value, _IPMB_NETFN_ZH)


def _localize_command(value: str) -> str:
    return _IPMB_COMMAND_ZH.get(value, value)


def _localize_summary(value: str) -> str:
    match = _SUMMARY_RE.fullmatch(value.strip())
    if not match:
        return value
    mctp_count, ipmb_count, unparsed_count = match.groups()
    localized = f"已解碼 {mctp_count} 個 MCTP 封包與 {ipmb_count} 個 IPMB frame"
    if unparsed_count:
        localized += f"；另有 {unparsed_count} 行輸入未解碼"
    return f"{localized}（{value}）"


def _localize_source_error(value: str) -> str:
    match = _INCOMPLETE_TOKEN_RE.fullmatch(value)
    if match:
        return f"第 {match.group(1)} 行：byte token 不完整：{match.group(2)}（{value}）"
    match = _UNRECOGNIZED_LINE_RE.fullmatch(value)
    if match:
        return f"第 {match.group(1)} 行：找不到可辨識的 MCTP 封包或 IPMB frame（{value}）"
    return value


def _localize_pldm_command(value: str) -> str:
    match = _PLDM_INFO_RE.fullmatch(value.strip())
    if not match:
        return value
    direction = "請求（Request）" if match.group("direction") == "Request" else "回應（Response）"
    localized = (
        f"PLDM {_localize_pldm_type(match.group('type'))} {direction}：命令（Cmd）{match.group('cmd')}"
        f"（Instance {match.group('instance')}）"
    )
    if match.group("cc"):
        localized += f"；完成碼（CC）{match.group('cc')}"
    return localized


def _localize_message_error(value: str) -> str:
    match = _SEQUENCE_MISMATCH_RE.fullmatch(value)
    if match:
        return f"序號不一致：預期 {match.group(1)}、實際 {match.group(2)}（{value}）"
    if value == "Orphan packet received without preceding SOM":
        return f"收到沒有前置 SOM 的孤立封包（{value}）"
    if value == "Incomplete message stream: missing EOM":
        return f"訊息串流不完整：缺少 EOM（{value}）"
    return value


def _localize_message_summary(value: str) -> str:
    match = _MCTP_PACKET_SUMMARY_RE.fullmatch(value.strip())
    if match:
        localized = (
            f"MCTP：EID {match.group('src')} -> {match.group('dest')} "
            f"[{_localize_msg_type(match.group('type'))}] Tag:{match.group('tag')}"
        )
        if match.group("pldm"):
            localized += f"（{_localize_pldm_command(match.group('pldm'))}）"
        return localized

    match = _MCTP_MESSAGE_SUMMARY_RE.fullmatch(value.strip())
    if match:
        localized = (
            f"MCTP 訊息：EID {match.group('src')} -> {match.group('dest')} "
            f"[{_localize_msg_type(match.group('type'))}]（{match.group('packets')} 個封包、"
            f"{match.group('bytes')} bytes）"
        )
        if match.group("pldm"):
            localized += f"（{_localize_pldm_command(match.group('pldm'))}）"
        if match.group("error"):
            localized += f"；錯誤：{_localize_message_error(match.group('error'))}"
        return localized

    match = _MCTP_ORPHAN_SUMMARY_RE.fullmatch(value.strip())
    if match:
        return f"MCTP：沒有 SOM 的孤立封包（Tag: {match.group('tag')}）"
    match = _MCTP_INCOMPLETE_SUMMARY_RE.fullmatch(value.strip())
    if match:
        return f"MCTP：來自 EID {match.group('src')} 的訊息不完整（缺少 EOM）"
    return value


def _localize_status(value: str) -> str:
    if value == "Complete":
        return "完成（Complete）"
    if value.startswith("Error: "):
        return f"錯誤（{_localize_message_error(value[7:])}）"
    return value


def _localize_checksum(value: str) -> str:
    if value == "OK":
        return "通過（OK）"
    if value == "FAIL":
        return "失敗（FAIL）"
    if value == "Checksum ERROR":
        return "Checksum 錯誤（Checksum ERROR）"
    return value


class ServerMgmtReporter:
    @staticmethod
    def render_terminal(report: ServerMgmtReport, console: Console | None = None) -> None:
        c = console or Console()
        c.print(
            Panel(
                "[bold cyan]⚡ 伺服器管理協定診斷報告（Server Management Protocol Diagnostic Report）[/]\n"
                f"{_localize_summary(report.summary_text)}"
            )
        )

        if report.source_errors:
            errors = Table(title="未解碼輸入行（Input Lines Not Decoded）", show_header=True)
            errors.add_column("來源（Source）", style="yellow")
            errors.add_column("原因（Reason）", style="red")
            for source, reason in zip(report.unparsed_lines, report.source_errors, strict=False):
                errors.add_row(source.strip(), _localize_source_error(reason))
                c.print(errors)

        if report.ambiguous_lines:
            amb_table = Table(
                title=("無法判定的 Frame（Ambiguous Frames (protocol cannot be determined)）"),
                show_header=True,
            )
            amb_table.add_column("來源行（Source Line）", style="red")
            for line in report.ambiguous_lines:
                amb_table.add_row(line)
                c.print(amb_table)

        if report.mctp_packets:
            mctp_tbl = Table(title="MCTP 封包（MCTP Packets）", show_header=True)
            mctp_tbl.add_column("#", justify="right", style="dim")
            mctp_tbl.add_column("來源 -> 目的（Src -> Dest）", style="cyan")
            mctp_tbl.add_column("訊息類型（Msg Type）", style="bold yellow")
            mctp_tbl.add_column("旗標（Flags）", style="dim")
            mctp_tbl.add_column("Payload 十六進位（Payload Hex）", style="white")
            mctp_tbl.add_column("細節（Details）", style="green")
            for idx, p in enumerate(report.mctp_packets, 1):
                flags_str = f"SOM:{int(p.som)} EOM:{int(p.eom)} Seq:{p.pkt_seq} Tag:{p.msg_tag}"
                mctp_tbl.add_row(
                    str(idx),
                    f"0x{p.src_eid:02X} -> 0x{p.dest_eid:02X}",
                    _localize_msg_type(p.msg_type_name),
                    flags_str,
                    p.payload_hex,
                    _localize_pldm_command(p.pldm_command) if p.pldm_command else "-",
                )
            c.print(mctp_tbl)

        multi_pkt_msgs = [
            m for m in report.mctp_messages if m.packets_count > 1 or not m.is_complete
        ]
        if multi_pkt_msgs:
            msg_tbl = Table(title="重組 MCTP 訊息（Reassembled MCTP Messages）", show_header=True)
            msg_tbl.add_column("#", justify="right", style="dim")
            msg_tbl.add_column("類型（Type）", style="cyan")
            msg_tbl.add_column("封包數（Pkts）", justify="right", style="yellow")
            msg_tbl.add_column("位元組數（Bytes）", justify="right", style="yellow")
            msg_tbl.add_column("狀態（Status）", style="bold")
            msg_tbl.add_column("摘要（Summary）", style="green")
            for idx, msg in enumerate(multi_pkt_msgs, 1):
                status = (
                    f"[green]{_localize_status('Complete')}[/]"
                    if msg.is_complete
                    else f"[red]{_localize_status(f'Error: {msg.error}')}[/]"
                )
                msg_tbl.add_row(
                    str(idx),
                    _localize_msg_type(msg.msg_type_name),
                    str(msg.packets_count),
                    str(len(msg.payload)),
                    status,
                    _localize_message_summary(msg.summary),
                )
            c.print(msg_tbl)

        if report.ipmb_frames:
            ipmb_tbl = Table(title="IPMB 框架（IPMB Frames）", show_header=True)
            ipmb_tbl.add_column("#", justify="right", style="dim")
            ipmb_tbl.add_column("請求 -> 回應（Rq -> Rs）", style="cyan")
            ipmb_tbl.add_column("網路功能（NetFn）", style="yellow")
            ipmb_tbl.add_column("命令（Command）", style="bold white")
            ipmb_tbl.add_column("檢查碼（Checksums）", style="dim")
            for idx, f in enumerate(report.ipmb_frames, 1):
                chk1_s = _localize_checksum("OK" if f.checksum1_valid else "FAIL")
                chk2_s = _localize_checksum("OK" if f.checksum2_valid else "FAIL")
                chk_str = f"CHK1:{chk1_s} CHK2:{chk2_s}"
                ipmb_tbl.add_row(
                    str(idx),
                    f"0x{f.rq_addr:02X} -> 0x{f.rs_addr:02X}",
                    _localize_netfn(f.netfn_name),
                    _localize_command(f.cmd_name),
                    chk_str,
                )
            c.print(ipmb_tbl)

    @staticmethod
    def to_markdown(report: ServerMgmtReport) -> str:
        lines = [
            (
                "# 伺服器管理協定診斷報告（Server Management Protocol Diagnostic Report）"
                "（MCTP / IPMB）\n"
            )
        ]
        lines.append(f"> **摘要（Summary）**: {_localize_summary(report.summary_text)}\n")

        if report.source_errors:
            lines.append("## 0. 未解碼輸入行（Input Lines Not Decoded）")
            lines.append("| 來源（Source） | 原因（Reason） |")
            lines.append("|---|---|")
            for source, reason in zip(report.unparsed_lines, report.source_errors, strict=False):
                lines.append(f"| `{source.strip()}` | {_localize_source_error(reason)} |")
            lines.append("")

        if report.mctp_packets:
            lines.append("## 1. MCTP 封包（MCTP Packets；DSP0236）")
            lines.append(
                "| # | 來源 EID（Src EID） | 目的 EID（Dest EID） | "
                "訊息類型（Message Type） | 旗標（Flags） | Payload | 細節（Details） |"
            )
            lines.append("|---|---|---|---|---|---|---|")
            for idx, p in enumerate(report.mctp_packets, 1):
                flags_str = f"SOM:{int(p.som)} EOM:{int(p.eom)} Seq:{p.pkt_seq} Tag:{p.msg_tag}"
                lines.append(
                    f"| #{idx} | `0x{p.src_eid:02X}` | `0x{p.dest_eid:02X}` | {_localize_msg_type(p.msg_type_name)} | {flags_str} | `{p.payload_hex}` | "
                    f"{_localize_pldm_command(p.pldm_command) if p.pldm_command else '-'} |"
                )
            lines.append("")

        multi_pkt_msgs = [
            m for m in report.mctp_messages if m.packets_count > 1 or not m.is_complete
        ]
        if multi_pkt_msgs:
            lines.append("## 1.1 重組 MCTP 訊息（Reassembled MCTP Messages）")
            lines.append(
                "| # | 類型（Type） | 封包數（Packets） | 位元組數（Bytes） | "
                "狀態（Status） | 摘要（Summary） |"
            )
            lines.append("|---|---|---|---|---|---|")
            for idx, msg in enumerate(multi_pkt_msgs, 1):
                status = _localize_status("Complete" if msg.is_complete else f"Error: {msg.error}")
                lines.append(
                    f"| {idx} | {_localize_msg_type(msg.msg_type_name)} | {msg.packets_count} | {len(msg.payload)} | "
                    f"{status} | {_localize_message_summary(msg.summary)} |"
                )
            lines.append("")

        if report.ipmb_frames:
            lines.append("## 2. IPMB 框架（IPMB Frames）")
            lines.append(
                "| # | 請求位址（Rq Addr） | 回應位址（Rs Addr） | NetFn | "
                "網路功能（NetFn） | 命令（Command） | 資料（Data） | 狀態（Status） |"
            )
            lines.append("|---|---|---|---|---|---|---|")
            for idx, f in enumerate(report.ipmb_frames, 1):
                data_str = " ".join(f"{b:02X}" for b in f.data) if f.data else "-"
                status_str = _localize_checksum(
                    "OK" if (f.checksum1_valid and f.checksum2_valid) else "Checksum ERROR"
                )
                lines.append(
                    f"| #{idx} | `0x{f.rq_addr:02X}` | `0x{f.rs_addr:02X}` | {_localize_netfn(f.netfn_name)} | {_localize_command(f.cmd_name)} | `{data_str}` | {status_str} |"
                )
            lines.append("")

        return "\n".join(lines)
