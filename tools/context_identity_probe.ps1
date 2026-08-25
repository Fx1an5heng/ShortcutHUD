[CmdletBinding()]
param(
    [ValidateRange(0, 60)] [int] $DelaySeconds = 3,
    [ValidateRange(1, 100)] [int] $Samples = 1,
    [ValidateRange(100, 60000)] [int] $IntervalMilliseconds = 1000,
    [ValidateRange(1, 64)] [int] $MaxUiaAncestors = 16,
    [ValidateRange(0, 500)] [int] $MaxChildWindows = 100,
    [switch] $IncludeCommandLine
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Development diagnostic for Context Identity research. It reports the current
# foreground window, focus, UIA ancestry, and related processes. It is not a
# ShortcutHUD production Context Detector, is not imported by ShortcutHUD,
# prints JSON only to stdout, and never reads terminal TextPattern contents or
# creates a log file.

$nativeMethods = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class ContextIdentityNative
{
    public delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    private struct RECT
    {
        public int left, top, right, bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct GUITHREADINFO
    {
        public uint cbSize;
        public uint flags;
        public IntPtr hwndActive;
        public IntPtr hwndFocus;
        public IntPtr hwndCapture;
        public IntPtr hwndMenuOwner;
        public IntPtr hwndMoveSize;
        public IntPtr hwndCaret;
        public RECT rcCaret;
    }

    public sealed class GuiInfo
    {
        public long ActiveHwnd { get; set; }
        public long FocusHwnd { get; set; }
        public long CaptureHwnd { get; set; }
        public long MenuOwnerHwnd { get; set; }
        public long CaretHwnd { get; set; }
    }

    public sealed class WindowInfo
    {
        public long Hwnd { get; set; }
        public long ParentHwnd { get; set; }
        public uint ProcessId { get; set; }
        public string ClassName { get; set; }
        public string Title { get; set; }
    }

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int maxCount);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr hwnd, StringBuilder className, int maxCount);

    [DllImport("user32.dll")]
    private static extern IntPtr GetParent(IntPtr hwnd);

    [DllImport("user32.dll")]
    private static extern bool EnumChildWindows(IntPtr parent, EnumWindowsProc callback, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool GetGUIThreadInfo(uint threadId, ref GUITHREADINFO info);

    private static string ReadText(IntPtr hwnd)
    {
        StringBuilder value = new StringBuilder(1024);
        GetWindowText(hwnd, value, value.Capacity);
        return value.ToString();
    }

    private static string ReadClass(IntPtr hwnd)
    {
        StringBuilder value = new StringBuilder(512);
        GetClassName(hwnd, value, value.Capacity);
        return value.ToString();
    }

    public static WindowInfo ReadWindow(IntPtr hwnd)
    {
        uint processId;
        GetWindowThreadProcessId(hwnd, out processId);
        return new WindowInfo {
            Hwnd = hwnd.ToInt64(),
            ParentHwnd = GetParent(hwnd).ToInt64(),
            ProcessId = processId,
            ClassName = ReadClass(hwnd),
            Title = ReadText(hwnd)
        };
    }

    public static GuiInfo ReadGuiInfo(IntPtr foregroundHwnd)
    {
        uint processId;
        uint threadId = GetWindowThreadProcessId(foregroundHwnd, out processId);
        GUITHREADINFO value = new GUITHREADINFO();
        value.cbSize = (uint)Marshal.SizeOf(value);
        if (!GetGUIThreadInfo(threadId, ref value)) return null;
        return new GuiInfo {
            ActiveHwnd = value.hwndActive.ToInt64(),
            FocusHwnd = value.hwndFocus.ToInt64(),
            CaptureHwnd = value.hwndCapture.ToInt64(),
            MenuOwnerHwnd = value.hwndMenuOwner.ToInt64(),
            CaretHwnd = value.hwndCaret.ToInt64()
        };
    }

    public static WindowInfo[] EnumerateChildren(IntPtr root, int maximum)
    {
        List<WindowInfo> windows = new List<WindowInfo>();
        if (maximum <= 0) return windows.ToArray();
        EnumWindowsProc callback = delegate(IntPtr hwnd, IntPtr lParam) {
            windows.Add(ReadWindow(hwnd));
            return windows.Count < maximum;
        };
        EnumChildWindows(root, callback, IntPtr.Zero);
        GC.KeepAlive(callback);
        return windows.ToArray();
    }
}
'@

Add-Type -TypeDefinition $nativeMethods -Language CSharp

$uiaAvailable = $true
$uiaLoadError = $null
try {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
}
catch {
    $uiaAvailable = $false
    $uiaLoadError = $_.Exception.Message
}

function Limit-ProbeText {
    param([AllowNull()] [string] $Value, [int] $Maximum = 160)
    if ($null -eq $Value -or $Value.Length -le $Maximum) { return $Value }
    return $Value.Substring(0, $Maximum) + "..."
}

function Convert-WindowInfo {
    param($Window)
    if ($null -eq $Window) { return $null }
    [ordered]@{
        hwnd = ('0x{0:X}' -f [long] $Window.Hwnd)
        parent_hwnd = ('0x{0:X}' -f [long] $Window.ParentHwnd)
        process_id = [uint32] $Window.ProcessId
        class_name = Limit-ProbeText $Window.ClassName
        title = Limit-ProbeText $Window.Title
    }
}

function Convert-ProcessInfo {
    param($Process)
    $result = [ordered]@{
        process_id = [uint32] $Process.ProcessId
        parent_process_id = [uint32] $Process.ParentProcessId
        exe_name = $Process.Name
        image_path = $Process.ExecutablePath
    }
    if ($IncludeCommandLine) {
        $result.command_line = Limit-ProbeText $Process.CommandLine 240
    }
    return $result
}

function Get-ProcessContext {
    param([uint32] $RootProcessId)

    try {
        $processProperties = @(
            "ProcessId",
            "ParentProcessId",
            "Name",
            "ExecutablePath"
        )
        if ($IncludeCommandLine) {
            $processProperties += "CommandLine"
        }
        $processes = @(
            Get-CimInstance Win32_Process -Property $processProperties -ErrorAction Stop
        )
        $byId = @{}
        $childrenByParent = @{}
        foreach ($process in $processes) {
            $byId[[uint32] $process.ProcessId] = $process
            $parentId = [uint32] $process.ParentProcessId
            if (-not $childrenByParent.ContainsKey($parentId)) {
                $childrenByParent[$parentId] = [System.Collections.Generic.List[object]]::new()
            }
            $childrenByParent[$parentId].Add($process)
        }

        $ancestors = [System.Collections.Generic.List[object]]::new()
        $seen = @{}
        $currentId = $RootProcessId
        while ($byId.ContainsKey($currentId) -and -not $seen.ContainsKey($currentId)) {
            $seen[$currentId] = $true
            $current = $byId[$currentId]
            $ancestors.Add((Convert-ProcessInfo $current))
            $currentId = [uint32] $current.ParentProcessId
        }

        $descendants = [System.Collections.Generic.List[object]]::new()
        $queue = [System.Collections.Generic.Queue[uint32]]::new()
        $queue.Enqueue($RootProcessId)
        while ($queue.Count -gt 0 -and $descendants.Count -lt 128) {
            $parentId = $queue.Dequeue()
            if (-not $childrenByParent.ContainsKey($parentId)) { continue }
            foreach ($child in $childrenByParent[$parentId]) {
                $descendants.Add((Convert-ProcessInfo $child))
                $queue.Enqueue([uint32] $child.ProcessId)
                if ($descendants.Count -ge 128) { break }
            }
        }

        [ordered]@{
            available = $true
            error = $null
            root_and_ancestors = $ancestors
            descendants = $descendants
            descendants_truncated = ($descendants.Count -ge 128)
        }
    }
    catch {
        [ordered]@{
            available = $false
            error = $_.Exception.Message
            root_and_ancestors = @()
            descendants = @()
            descendants_truncated = $false
        }
    }
}

function Convert-UiaElement {
    param($Element, [int] $Depth)
    try {
        $current = $Element.Current
        [ordered]@{
            depth = $Depth
            name = Limit-ProbeText $current.Name
            automation_id = Limit-ProbeText $current.AutomationId
            class_name = Limit-ProbeText $current.ClassName
            control_type = $current.ControlType.ProgrammaticName
            framework_id = $current.FrameworkId
            process_id = $current.ProcessId
            native_window_handle = ('0x{0:X}' -f [long] $current.NativeWindowHandle)
            has_keyboard_focus = $current.HasKeyboardFocus
            is_keyboard_focusable = $current.IsKeyboardFocusable
        }
    }
    catch {
        [ordered]@{ depth = $Depth; error = $_.Exception.Message }
    }
}

function Get-UiaFocusContext {
    if (-not $uiaAvailable) {
        return [ordered]@{ available = $false; error = $uiaLoadError; focused_and_ancestors = @() }
    }
    try {
        $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
        if ($null -eq $focused) {
            return [ordered]@{
                available = $true
                error = "UI Automation returned no focused element."
                focused_and_ancestors = @()
            }
        }
        $elements = [System.Collections.Generic.List[object]]::new()
        $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
        $current = $focused
        for ($depth = 0; $depth -lt $MaxUiaAncestors -and $null -ne $current; $depth++) {
            $elements.Add((Convert-UiaElement $current $depth))
            $current = $walker.GetParent($current)
        }
        [ordered]@{ available = $true; error = $null; focused_and_ancestors = $elements }
    }
    catch {
        [ordered]@{ available = $true; error = $_.Exception.Message; focused_and_ancestors = @() }
    }
}

if ($DelaySeconds -gt 0) {
    Write-Host "Focus the target terminal pane now; sampling starts in $DelaySeconds second(s)." -ForegroundColor Yellow
    Start-Sleep -Seconds $DelaySeconds
}

for ($sampleIndex = 1; $sampleIndex -le $Samples; $sampleIndex++) {
    $totalWatch = [System.Diagnostics.Stopwatch]::StartNew()

    $windowWatch = [System.Diagnostics.Stopwatch]::StartNew()
    $foregroundHwnd = [ContextIdentityNative]::GetForegroundWindow()
    $foregroundWindow = [ContextIdentityNative]::ReadWindow($foregroundHwnd)
    $guiInfo = [ContextIdentityNative]::ReadGuiInfo($foregroundHwnd)
    $focusWindow = $null
    if ($null -ne $guiInfo -and $guiInfo.FocusHwnd -ne 0) {
        $focusWindow = [ContextIdentityNative]::ReadWindow([IntPtr] $guiInfo.FocusHwnd)
    }
    $windowWatch.Stop()

    $uiaWatch = [System.Diagnostics.Stopwatch]::StartNew()
    $uia = Get-UiaFocusContext
    $uiaWatch.Stop()

    $childrenWatch = [System.Diagnostics.Stopwatch]::StartNew()
    $childWindows = @(
        [ContextIdentityNative]::EnumerateChildren($foregroundHwnd, $MaxChildWindows) |
            ForEach-Object { Convert-WindowInfo $_ }
    )
    $childrenWatch.Stop()

    $processWatch = [System.Diagnostics.Stopwatch]::StartNew()
    $processContext = Get-ProcessContext ([uint32] $foregroundWindow.ProcessId)
    $processWatch.Stop()
    $totalWatch.Stop()

    [ordered]@{
        probe = "ShortcutHUD Phase 6A context identity probe"
        captured_at = [DateTimeOffset]::Now.ToString("o")
        sample = $sampleIndex
        foreground_window = Convert-WindowInfo $foregroundWindow
        win32_gui_thread = if ($null -eq $guiInfo) { $null } else {
            [ordered]@{
                active_hwnd = ('0x{0:X}' -f [long] $guiInfo.ActiveHwnd)
                focus_hwnd = ('0x{0:X}' -f [long] $guiInfo.FocusHwnd)
                capture_hwnd = ('0x{0:X}' -f [long] $guiInfo.CaptureHwnd)
                menu_owner_hwnd = ('0x{0:X}' -f [long] $guiInfo.MenuOwnerHwnd)
                caret_hwnd = ('0x{0:X}' -f [long] $guiInfo.CaretHwnd)
            }
        }
        focus_window = Convert-WindowInfo $focusWindow
        uia = $uia
        child_windows = $childWindows
        child_windows_truncated = ($MaxChildWindows -gt 0 -and $childWindows.Count -ge $MaxChildWindows)
        process_context = $processContext
        timings_ms = [ordered]@{
            foreground_and_focus = [Math]::Round($windowWatch.Elapsed.TotalMilliseconds, 3)
            uia_focus_and_ancestors = [Math]::Round($uiaWatch.Elapsed.TotalMilliseconds, 3)
            child_windows = [Math]::Round($childrenWatch.Elapsed.TotalMilliseconds, 3)
            process_snapshot = [Math]::Round($processWatch.Elapsed.TotalMilliseconds, 3)
            total = [Math]::Round($totalWatch.Elapsed.TotalMilliseconds, 3)
        }
        notes = @(
            "UIA TextPattern and terminal screen contents are intentionally not read.",
            "Window, tab, and UIA element names may contain user-selected titles; review output before sharing.",
            "Windows process ancestry cannot identify programs on a remote Xshell host or inside WSL from the host HWND alone."
        )
    } | ConvertTo-Json -Depth 12

    if ($sampleIndex -lt $Samples) {
        Start-Sleep -Milliseconds $IntervalMilliseconds
    }
}
