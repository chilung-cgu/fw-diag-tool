"""Knowledge base for common UART boot and crash symptoms."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class UARTSymptom:
    pattern: str
    category: str
    severity: Literal["critical", "warning", "info"]
    description_zh: str
    description_en: str
    suggested_action_zh: str
    suggested_action_en: str


@dataclass(frozen=True)
class MatchedSymptom:
    symptom: UARTSymptom
    matched_line: str
    line_number: int


SYMPTOM_DB: list[UARTSymptom] = [
    UARTSymptom(
        r"kernel\s+panic",
        "kernel_panic",
        "critical",
        "Linux 核心已進入 Panic。",
        "The Linux kernel entered a panic state.",
        "保留完整 call trace，使用相同版本的符號檔分析故障點。",
        "Preserve the full call trace and analyze it with matching symbols.",
    ),
    UARTSymptom(
        r"\bOops:",
        "kernel_panic",
        "critical",
        "偵測到 Linux 核心 Oops 例外。",
        "A Linux kernel Oops exception was reported.",
        "檢查 Oops 前後的暫存器、堆疊與模組資訊。",
        "Inspect registers, stack data, and module information around the Oops.",
    ),
    UARTSymptom(
        r"BUG:\s+unable\s+to\s+handle",
        "kernel_panic",
        "critical",
        "核心無法處理記憶體或分頁錯誤。",
        "The kernel could not handle a memory or paging fault.",
        "核對 fault address、指令位址與對應的核心原始碼。",
        "Correlate the fault address and instruction pointer with kernel sources.",
    ),
    UARTSymptom(
        r"fatal\s+exception",
        "kernel_panic",
        "critical",
        "開機或執行期間發生致命例外。",
        "A fatal exception occurred during boot or execution.",
        "確認例外架構與完整堆疊，並檢查最近的韌體變更。",
        "Capture the complete stack and review recent firmware changes.",
    ),
    UARTSymptom(
        r"watchdog(?:\s+timer)?[\s:.-]*(?:timeout|timed\s*out|expired)",
        "watchdog",
        "critical",
        "Watchdog 逾時，表示系統未在期限內回應。",
        "A watchdog timeout indicates the system failed to respond in time.",
        "檢查卡住的執行緒、ISR 延遲與 watchdog 設定。",
        "Inspect stuck threads, ISR latency, and watchdog configuration.",
    ),
    UARTSymptom(
        r"watchdog(?:\s+timer)?[\s:.-]*(?:reset|reboot)",
        "watchdog",
        "critical",
        "系統由 Watchdog 觸發重置。",
        "The system was reset by a watchdog.",
        "比對重置原因暫存器並保留重置前最後一段 UART 輸出。",
        "Read reset-cause registers and preserve the final UART output before reset.",
    ),
    UARTSymptom(
        r"\bwdt\b.*\b(?:timeout|reset)\b",
        "watchdog",
        "warning",
        "日誌指出 WDT/Watchdog 可能逾時或重置。",
        "The log indicates a possible WDT/watchdog timeout or reset.",
        "確認餵狗路徑與系統負載，並增加必要的診斷記錄。",
        "Check the watchdog feed path and system load, adding diagnostics as needed.",
    ),
    UARTSymptom(
        r"(?:soft|hard)\s+lockup\s+detected",
        "watchdog",
        "critical",
        "核心偵測到執行緒或 CPU lockup。",
        "The kernel detected a thread or CPU lockup.",
        "檢查 lockup 堆疊、死結與長時間停用中斷的區段。",
        "Inspect the lockup stack, deadlocks, and long interrupt-disabled sections.",
    ),
    UARTSymptom(
        r"out\s+of\s+memory",
        "oom",
        "critical",
        "系統可用記憶體耗盡。",
        "System memory was exhausted.",
        "檢查記憶體用量、cgroup 限制與是否需要降低工作集。",
        "Inspect memory usage, cgroup limits, and workload size.",
    ),
    UARTSymptom(
        r"oom[- ]killer",
        "oom",
        "critical",
        "Linux OOM killer 已開始終止程序。",
        "The Linux OOM killer started terminating processes.",
        "查看被終止程序及其 RSS，並追查記憶體洩漏。",
        "Review the killed process RSS and investigate memory leaks.",
    ),
    UARTSymptom(
        r"killed\s+process\s+.+(?:out\s+of\s+memory|oom)",
        "oom",
        "critical",
        "程序因 OOM 被核心終止。",
        "A process was killed by the kernel because of OOM.",
        "記錄程序記憶體峰值並檢查配置的記憶體上限。",
        "Record the process memory peak and check configured memory limits.",
    ),
    UARTSymptom(
        r"cannot\s+allocate\s+memory|allocation\s+failed",
        "oom",
        "warning",
        "記憶體配置失敗。",
        "A memory allocation failed.",
        "檢查可用記憶體、碎片化與配置大小。",
        "Check free memory, fragmentation, and allocation size.",
    ),
    UARTSymptom(
        r"(?:ext[234]|xfs|btrfs)-fs\s+error",
        "filesystem",
        "critical",
        "檔案系統回報嚴重錯誤。",
        "The filesystem reported a serious error.",
        "以唯讀方式檢查檔案系統並確認儲存媒體健康狀態。",
        "Check the filesystem read-only and verify storage health.",
    ),
    UARTSymptom(
        r"I/O\s+error.*(?:sector|block|device)",
        "filesystem",
        "critical",
        "儲存裝置發生 I/O 錯誤。",
        "A storage device reported an I/O error.",
        "檢查裝置連線、媒體壽命與 SMART/錯誤計數。",
        "Check device connectivity, media wear, and SMART/error counters.",
    ),
    UARTSymptom(
        r"read-only\s+file\s+system",
        "filesystem",
        "warning",
        "檔案系統已切換為唯讀。",
        "The filesystem was remounted read-only.",
        "追查造成重新掛載的 I/O 或 journal 錯誤，再安排檔案系統修復。",
        "Trace the I/O or journal error and schedule filesystem repair.",
    ),
    UARTSymptom(
        r"VFS:.*unable\s+to\s+mount",
        "filesystem",
        "critical",
        "核心無法掛載必要的檔案系統。",
        "The kernel could not mount a required filesystem.",
        "核對 root= 參數、分割區 UUID、檔案系統驅動與 initramfs。",
        "Check root=, partition UUID, filesystem drivers, and initramfs.",
    ),
    UARTSymptom(
        r"(?:probe|driver)\s+(?:failed|error)|probe\s+defer(?:red)?",
        "driver_probe",
        "warning",
        "裝置驅動 probe 失敗或被延後。",
        "A device driver probe failed or was deferred.",
        "檢查 probe 錯誤碼、電源/時鐘資源與 Device Tree。",
        "Inspect the probe error code, power/clock resources, and Device Tree.",
    ),
    UARTSymptom(
        r"failed\s+to\s+(?:load|request)\s+firmware",
        "driver_probe",
        "warning",
        "驅動程式無法載入所需韌體。",
        "A driver could not load its required firmware.",
        "確認韌體檔案存在、版本相容且已打包進 rootfs。",
        "Verify the firmware file exists, is compatible, and is in the rootfs.",
    ),
    UARTSymptom(
        r"no\s+such\s+device",
        "driver_probe",
        "warning",
        "核心找不到指定的硬體裝置。",
        "The kernel could not find the requested hardware device.",
        "核對匯流排枚舉、裝置位址、reset 與供電狀態。",
        "Check bus enumeration, device address, reset, and power state.",
    ),
    UARTSymptom(
        r"deferred\s+probe\s+pending",
        "driver_probe",
        "info",
        "驅動 probe 等待相依資源後重試。",
        "The driver probe is waiting for a dependency and will retry.",
        "確認相依 regulator、clock 或 supplier 驅動最終成功。",
        "Verify the dependent regulator, clock, or supplier driver eventually succeeds.",
    ),
    UARTSymptom(
        r"machine\s+check|mce:\s",
        "hardware_error",
        "critical",
        "CPU 回報 Machine Check 硬體錯誤。",
        "The CPU reported a machine-check hardware error.",
        "保存 MCE 詳細欄位並檢查 CPU、記憶體與主機板硬體。",
        "Capture MCE details and inspect CPU, memory, and board hardware.",
    ),
    UARTSymptom(
        r"hardware\s+error|hardware\s+fault",
        "hardware_error",
        "critical",
        "日誌回報未分類硬體錯誤。",
        "The log reported an unspecified hardware error.",
        "比對硬體錯誤暫存器、電源軌與溫度遙測資料。",
        "Correlate hardware error registers with power rails and telemetry.",
    ),
    UARTSymptom(
        r"uncorrectable\s+(?:ecc\s+)?error|ecc\s+uncorrectable",
        "hardware_error",
        "critical",
        "偵測到無法修正的 ECC 錯誤。",
        "An uncorrectable ECC error was detected.",
        "隔離故障 DIMM/記憶體並檢查 ECC 計數器與硬體連線。",
        "Quarantine the failing DIMM/memory and check ECC counters and connections.",
    ),
    UARTSymptom(
        r"(?:overheat|overtemperature|temperature).*(?:critical|shutdown|trip)",
        "hardware_error",
        "critical",
        "硬體溫度達到臨界或保護關機門檻。",
        "Hardware temperature reached a critical or shutdown threshold.",
        "檢查散熱、風扇、溫度感測器與熱保護設定。",
        "Check cooling, fans, temperature sensors, and thermal thresholds.",
    ),
    UARTSymptom(
        r"(?:unable|failed)\s+to\s+(?:execute|run)\s+(?:/sbin/)?init",
        "boot_failure",
        "critical",
        "核心無法啟動 init 程序。",
        "The kernel could not start the init process.",
        "檢查 rootfs 中的 init 路徑、動態連結器與執行權限。",
        "Check the init path, dynamic linker, and execute permissions in rootfs.",
    ),
    UARTSymptom(
        r"no\s+bootable\s+device|no\s+boot\s+device",
        "boot_failure",
        "critical",
        "韌體找不到可開機裝置。",
        "Firmware could not find a bootable device.",
        "核對 boot order、儲存裝置枚舉與開機媒體內容。",
        "Check boot order, storage enumeration, and boot media contents.",
    ),
    UARTSymptom(
        r"(?:kernel|linux)\s+(?:image\s+)?not\s+found",
        "boot_failure",
        "critical",
        "Bootloader 找不到核心映像。",
        "The bootloader could not find a kernel image.",
        "確認 boot 路徑、分割區與核心映像檔名。",
        "Verify the boot path, partition, and kernel image filename.",
    ),
    UARTSymptom(
        r"failed\s+to\s+mount\s+(?:root|rootfs|/)",
        "boot_failure",
        "critical",
        "開機流程無法掛載 root 檔案系統。",
        "The boot process could not mount the root filesystem.",
        "核對 kernel command line、rootfs 驅動與儲存裝置就緒順序。",
        "Check the kernel command line, rootfs driver, and device readiness order.",
    ),
    UARTSymptom(
        r"permission\s+denied",
        "security_violation",
        "warning",
        "操作因權限不足被拒絕。",
        "An operation was denied because of insufficient permissions.",
        "核對檔案權限、SELinux/AppArmor 規則與執行身分。",
        "Check file permissions, SELinux/AppArmor rules, and execution identity.",
    ),
    UARTSymptom(
        r"avc:\s*denied",
        "security_violation",
        "warning",
        "SELinux 回報存取違規。",
        "SELinux reported an access violation.",
        "檢查 AVC 記錄並以最小權限更新安全性原則。",
        "Review the AVC record and update policy with least privilege.",
    ),
    UARTSymptom(
        r"secure\s+boot.*(?:fail|violation|invalid)|boot\s+verification\s+failed",
        "security_violation",
        "critical",
        "Secure Boot 驗證失敗或遭到違規。",
        "Secure Boot verification failed or was violated.",
        "確認簽章鏈、金鑰、映像完整性與安全開機設定。",
        "Verify the signing chain, keys, image integrity, and Secure Boot settings.",
    ),
    UARTSymptom(
        r"(?:signature|image)\s+verification\s+failed|invalid\s+signature",
        "security_violation",
        "critical",
        "映像或簽章驗證失敗。",
        "Image or signature verification failed.",
        "重新驗證映像雜湊、簽章格式與信任根金鑰。",
        "Recheck the image hash, signature format, and trusted root key.",
    ),
    UARTSymptom(
        r"segmentation\s+fault|segfault",
        "memory_error",
        "critical",
        "程序存取了無效記憶體位址。",
        "A process accessed an invalid memory address.",
        "使用 core dump、gdb 與符號檔定位故障指標。",
        "Use a core dump, gdb, and symbols to locate the invalid pointer.",
    ),
    UARTSymptom(
        r"bus\s+error",
        "memory_error",
        "critical",
        "程序觸發記憶體匯流排錯誤。",
        "A process triggered a memory bus error.",
        "檢查未對齊存取、MMU 屬性與底層硬體錯誤。",
        "Check unaligned access, MMU attributes, and underlying hardware errors.",
    ),
    UARTSymptom(
        r"memory\s+fault|page\s+fault",
        "memory_error",
        "critical",
        "偵測到記憶體或分頁錯誤。",
        "A memory or page fault was detected.",
        "核對 fault address、存取權限與對應的映射。",
        "Check the fault address, access permissions, and mapping.",
    ),
    UARTSymptom(
        r"stack\s+smashing\s+detected|stack\s+overflow",
        "memory_error",
        "critical",
        "偵測到堆疊毀損或堆疊溢位。",
        "Stack corruption or overflow was detected.",
        "檢查遞迴、區域緩衝區、stack canary 與執行緒堆疊大小。",
        "Inspect recursion, local buffers, stack canaries, and thread stack size.",
    ),
]


def classify_symptoms(lines: list[str]) -> list[MatchedSymptom]:
    """Match every symptom pattern against each input line."""
    matches: list[MatchedSymptom] = []
    for line_number, line in enumerate(lines, start=1):
        for symptom in SYMPTOM_DB:
            if re.search(symptom.pattern, line, re.IGNORECASE):
                matches.append(MatchedSymptom(symptom, line, line_number))
    return matches


__all__ = ["SYMPTOM_DB", "MatchedSymptom", "UARTSymptom", "classify_symptoms"]
