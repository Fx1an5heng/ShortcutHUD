[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Output,

    [ValidateRange(0, 1000)]
    [int]$BenchmarkIterations = 0,

    [ValidateRange(1, 200)]
    [int]$MaxAncestryDepth = 40,

    [ValidateRange(1, 500)]
    [int]$MaxTabElements = 100,

    [ValidateRange(1, 100)]
    [int]$MaxTabChildren = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

if (-not ('ShortcutHudUiaNativeMethods' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class ShortcutHudUiaNativeMethods
{
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();
}
'@
}

$script:PatternDefinitions = @(
    [pscustomobject]@{ Name = 'TextPattern'; Id = 10014 },
    [pscustomobject]@{ Name = 'TextPattern2'; Id = 10024 },
    [pscustomobject]@{ Name = 'ScrollPattern'; Id = 10004 },
    [pscustomobject]@{ Name = 'SelectionPattern'; Id = 10001 },
    [pscustomobject]@{ Name = 'SelectionItemPattern'; Id = 10010 },
    [pscustomobject]@{ Name = 'ValuePattern'; Id = 10002 },
    [pscustomobject]@{ Name = 'RangeValuePattern'; Id = 10003 },
    [pscustomobject]@{ Name = 'InvokePattern'; Id = 10000 },
    [pscustomobject]@{ Name = 'LegacyIAccessiblePattern'; Id = 10018 }
)

function Convert-UiaValue {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) {
        return $null
    }
    if ($Value -eq [System.Windows.Automation.AutomationElement]::NotSupported) {
        return $null
    }
    if ($Value -is [System.Windows.Automation.ControlType]) {
        return $Value.ProgrammaticName
    }
    if ($Value -is [System.Windows.Rect]) {
        if ($Value.IsEmpty) {
            return $null
        }
        return [ordered]@{
            X = $Value.X
            Y = $Value.Y
            Width = $Value.Width
            Height = $Value.Height
            Left = $Value.Left
            Top = $Value.Top
            Right = $Value.Right
            Bottom = $Value.Bottom
        }
    }
    if ($Value -is [System.Array]) {
        return @($Value | ForEach-Object { Convert-UiaValue $_ })
    }
    return $Value
}

function Get-UiaPropertyValue {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Element,

        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationProperty]$Property
    )

    try {
        return Convert-UiaValue (
            $Element.GetCurrentPropertyValue($Property, $true)
        )
    }
    catch {
        return $null
    }
}

function Get-UiaSupportedPatterns {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Element
    )

    try {
        $supported = @($Element.GetSupportedPatterns())
        $ids = @($supported | ForEach-Object { $_.Id })
        $result = [ordered]@{}
        foreach ($definition in $script:PatternDefinitions) {
            $result[$definition.Name] = $ids -contains $definition.Id
        }
        $result['AllSupported'] = @(
            $supported | ForEach-Object {
                [ordered]@{
                    Id = $_.Id
                    ProgrammaticName = $_.ProgrammaticName
                }
            }
        )
        return $result
    }
    catch {
        return [ordered]@{
            Status = 'unavailable'
            Error = $_.Exception.Message
        }
    }
}

function Get-UiaLegacyAccessibility {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Element,

        [Parameter(Mandatory = $true)]
        [object]$Patterns
    )

    if (-not $Patterns.LegacyIAccessiblePattern) {
        return [ordered]@{
            Supported = $false
            Role = $null
            State = $null
            Name = $null
            Value = $null
            Description = $null
            DefaultAction = $null
        }
    }

    $propertyMap = [ordered]@{
        Role = 'RoleProperty'
        State = 'StateProperty'
        Name = 'NameProperty'
        Value = 'ValueProperty'
        Description = 'DescriptionProperty'
        DefaultAction = 'DefaultActionProperty'
    }
    $supportedProperties = @()
    try {
        $supportedProperties = @($Element.GetSupportedProperties())
    }
    catch {
        $supportedProperties = @()
    }

    $result = [ordered]@{ Supported = $true }
    foreach ($entry in $propertyMap.GetEnumerator()) {
        $property = $supportedProperties |
            Where-Object {
                $_.ProgrammaticName -match 'LegacyIAccessible' -and
                $_.ProgrammaticName -like ('*' + $entry.Value)
            } |
            Select-Object -First 1
        if ($null -eq $property) {
            $result[$entry.Key] = $null
        }
        else {
            $result[$entry.Key] = Get-UiaPropertyValue $Element $property
        }
    }
    return $result
}

function Get-UiaElementRecord {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Element,

        [int]$Depth = 0
    )

    $patterns = Get-UiaSupportedPatterns $Element
    return [ordered]@{
        Depth = $Depth
        Name = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::NameProperty
        )
        AutomationId = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::AutomationIdProperty
        )
        ClassName = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::ClassNameProperty
        )
        FrameworkId = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::FrameworkIdProperty
        )
        ControlType = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty
        )
        LocalizedControlType = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::LocalizedControlTypeProperty
        )
        NativeWindowHandle = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::NativeWindowHandleProperty
        )
        ProcessId = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::ProcessIdProperty
        )
        IsEnabled = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::IsEnabledProperty
        )
        IsOffscreen = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::IsOffscreenProperty
        )
        BoundingRectangle = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::BoundingRectangleProperty
        )
        HelpText = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::HelpTextProperty
        )
        ItemType = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::ItemTypeProperty
        )
        ItemStatus = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::ItemStatusProperty
        )
        AccessKey = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::AccessKeyProperty
        )
        AcceleratorKey = Get-UiaPropertyValue $Element (
            [System.Windows.Automation.AutomationElement]::AcceleratorKeyProperty
        )
        Patterns = $patterns
        LegacyIAccessible = Get-UiaLegacyAccessibility $Element $patterns
    }
}

function Test-UiaSameElement {
    param(
        [AllowNull()][System.Windows.Automation.AutomationElement]$First,
        [AllowNull()][System.Windows.Automation.AutomationElement]$Second
    )

    if ($null -eq $First -or $null -eq $Second) {
        return $false
    }
    try {
        return [System.Windows.Automation.Automation]::Compare($First, $Second)
    }
    catch {
        return $false
    }
}

function Get-UiaAncestry {
    param(
        [AllowNull()][System.Windows.Automation.AutomationElement]$Start,
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Root,
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.TreeWalker]$Walker,
        [Parameter(Mandatory = $true)]
        [string]$ViewName,
        [int]$MaximumDepth = 40
    )

    $nodes = @()
    $errors = @()
    $current = $Start
    $reachedRoot = $false
    for ($depth = 0; $depth -lt $MaximumDepth -and $null -ne $current; $depth++) {
        try {
            $nodes += Get-UiaElementRecord $current $depth
            if (Test-UiaSameElement $current $Root) {
                $reachedRoot = $true
                break
            }
            $current = $Walker.GetParent($current)
        }
        catch {
            $errors += $_.Exception.Message
            break
        }
    }
    return [ordered]@{
        View = $ViewName
        ReachedForegroundRoot = $reachedRoot
        Nodes = $nodes
        Errors = $errors
    }
}

function Get-UiaImmediateChildren {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Element,
        [int]$Maximum = 30
    )

    $children = @()
    try {
        $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
        $child = $walker.GetFirstChild($Element)
        while ($null -ne $child -and $children.Count -lt $Maximum) {
            $children += Get-UiaElementRecord $child 0
            $child = $walker.GetNextSibling($child)
        }
    }
    catch {
        return [ordered]@{
            Status = 'failed'
            Error = $_.Exception.Message
            Items = $children
        }
    }
    return [ordered]@{
        Status = 'ok'
        Items = $children
    }
}

function Get-UiaSelectionState {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Element
    )

    $selectionItemObject = $null
    try {
        if ($Element.TryGetCurrentPattern(
                [System.Windows.Automation.SelectionItemPattern]::Pattern,
                [ref]$selectionItemObject
            )) {
            return [ordered]@{
                Pattern = 'SelectionItemPattern'
                IsSelected = $selectionItemObject.Current.IsSelected
                SelectedElements = @()
            }
        }
    }
    catch {
        return [ordered]@{
            Pattern = 'SelectionItemPattern'
            Error = $_.Exception.Message
        }
    }

    $selectionObject = $null
    try {
        if ($Element.TryGetCurrentPattern(
                [System.Windows.Automation.SelectionPattern]::Pattern,
                [ref]$selectionObject
            )) {
            $selected = @($selectionObject.Current.GetSelection())
            return [ordered]@{
                Pattern = 'SelectionPattern'
                IsSelected = $null
                SelectedElements = @(
                    $selected | ForEach-Object { Get-UiaElementRecord $_ 0 }
                )
            }
        }
    }
    catch {
        return [ordered]@{
            Pattern = 'SelectionPattern'
            Error = $_.Exception.Message
        }
    }
    return [ordered]@{
        Pattern = $null
        IsSelected = $null
        SelectedElements = @()
    }
}

function Find-UiaTabs {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Root,
        [int]$MaximumElements = 100,
        [int]$MaximumChildren = 30
    )

    $items = @()
    $errors = @()
    foreach ($controlType in @(
            [System.Windows.Automation.ControlType]::Tab,
            [System.Windows.Automation.ControlType]::TabItem
        )) {
        try {
            $condition = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                $controlType
            )
            $matches = $Root.FindAll(
                [System.Windows.Automation.TreeScope]::Descendants,
                $condition
            )
            foreach ($element in $matches) {
                if ($items.Count -ge $MaximumElements) {
                    break
                }
                $record = Get-UiaElementRecord $element 0
                $record['Selection'] = Get-UiaSelectionState $element
                $record['Children'] = Get-UiaImmediateChildren (
                    $element
                ) $MaximumChildren
                $items += $record
            }
        }
        catch {
            $errors += $_.Exception.Message
        }
    }
    return [ordered]@{
        Status = if ($errors.Count -eq 0) { 'ok' } else { 'partial' }
        Items = $items
        Errors = $errors
        Truncated = $items.Count -ge $MaximumElements
    }
}

function Get-UiaNarrowSemanticSample {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Root,
        [int]$MaximumDepth = 40
    )

    $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
    return [ordered]@{
        Focused = if ($null -eq $focused) {
            $null
        }
        else {
            Get-UiaElementRecord $focused 0
        }
        ControlAncestry = Get-UiaAncestry (
            $focused
        ) $Root (
            [System.Windows.Automation.TreeWalker]::ControlViewWalker
        ) 'ControlView' $MaximumDepth
        RawAncestry = Get-UiaAncestry (
            $focused
        ) $Root (
            [System.Windows.Automation.TreeWalker]::RawViewWalker
        ) 'RawView' $MaximumDepth
    }
}
function Get-UiaIdentityClassPath {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Root,
        [int]$MaximumDepth = 40
    )
    $focused = [System.Windows.Automation.AutomationElement]::FocusedElement
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $nodes = @()
    $current = $focused
    $reachedRoot = $false
    for ($depth = 0; $depth -lt $MaximumDepth -and $null -ne $current; $depth++) {
        $nodes += [ordered]@{
            Depth = $depth
            ClassName = Get-UiaPropertyValue $current (
                [System.Windows.Automation.AutomationElement]::ClassNameProperty
            )
        }
        if (Test-UiaSameElement $current $Root) {
            $reachedRoot = $true
            break
        }
        $current = $walker.GetParent($current)
    }
    return [ordered]@{
        ReachedForegroundRoot = $reachedRoot
        Nodes = $nodes
    }
}

function Get-Percentile {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [double[]]$SortedValues,
        [Parameter(Mandatory = $true)]
        [double]$Percentile
    )

    if ($SortedValues.Count -eq 0) {
        return $null
    }
    $index = [Math]::Ceiling($Percentile * $SortedValues.Count) - 1
    return $SortedValues[[Math]::Max(0, [int]$index)]
}

function Measure-UiaNarrowPath {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Root,
        [int]$Iterations,
        [int]$MaximumDepth
    )
    if ($Iterations -le 0) {
        return $null
    }
    $samples = New-Object System.Collections.Generic.List[double]
    $rootBoundSamples = New-Object System.Collections.Generic.List[double]
    $pdfCandidateSamples = New-Object System.Collections.Generic.List[double]
    $errors = @()
    $lastPath = $null
    $rootBoundIterations = 0
    $pdfCandidateIterations = 0
    $foreignFocusIterations = 0
    $unavailableIterations = 0
    for ($index = 0; $index -lt $Iterations; $index++) {
        $path = $null
        $stopwatch = [Diagnostics.Stopwatch]::StartNew()
        try {
            $path = Get-UiaIdentityClassPath $Root $MaximumDepth
            $lastPath = $path
        }
        catch {
            $errors += $_.Exception.Message
        }
        finally {
            $stopwatch.Stop()
            $duration = $stopwatch.Elapsed.TotalMilliseconds
            $samples.Add($duration)
        }
        if ($null -eq $path) {
            $unavailableIterations++
            continue
        }
        if (-not $path.ReachedForegroundRoot) {
            $foreignFocusIterations++
            continue
        }
        $rootBoundIterations++
        $rootBoundSamples.Add($duration)
        $classes = @($path.Nodes | ForEach-Object { $_.ClassName })
        $isPdfCandidate = (
            $classes.Count -gt 0 -and
            $classes[0] -eq 'KxPdfView' -and
            $classes -contains 'KxPdfDocPane' -and
            $classes -contains 'KxPdfMainWindow'
        )
        if ($isPdfCandidate) {
            $pdfCandidateIterations++
            $pdfCandidateSamples.Add($duration)
        }
    }
    $ordered = @($samples | Sort-Object)
    $orderedRootBound = @($rootBoundSamples | Sort-Object)
    $orderedPdf = @($pdfCandidateSamples | Sort-Object)
    return [ordered]@{
        Iterations = $Iterations
        RootBoundIterations = $rootBoundIterations
        PdfCandidateIterations = $pdfCandidateIterations
        ForeignFocusIterations = $foreignFocusIterations
        UnavailableIterations = $unavailableIterations
        MedianMs = Get-Percentile $ordered 0.50
        P95Ms = Get-Percentile $ordered 0.95
        MaxMs = if ($ordered.Count) { $ordered[-1] } else { $null }
        Over20Ms = @($ordered | Where-Object { $_ -gt 20 }).Count
        Over50Ms = @($ordered | Where-Object { $_ -gt 50 }).Count
        RootBoundMedianMs = Get-Percentile $orderedRootBound 0.50
        RootBoundP95Ms = Get-Percentile $orderedRootBound 0.95
        PdfCandidateMedianMs = Get-Percentile $orderedPdf 0.50
        PdfCandidateP95Ms = Get-Percentile $orderedPdf 0.95
        PdfCandidateMaxMs = if ($orderedPdf.Count) {
            $orderedPdf[-1]
        }
        else {
            $null
        }
        PdfCandidateOver20Ms = @(
            $orderedPdf | Where-Object { $_ -gt 20 }
        ).Count
        PdfCandidateOver50Ms = @(
            $orderedPdf | Where-Object { $_ -gt 50 }
        ).Count
        LastPath = $lastPath
        Errors = $errors
    }
}

$foregroundHwnd = [ShortcutHudUiaNativeMethods]::GetForegroundWindow()
if ($foregroundHwnd -eq [IntPtr]::Zero) {
    throw 'GetForegroundWindow returned no HWND.'
}

$root = [System.Windows.Automation.AutomationElement]::FromHandle(
    $foregroundHwnd
)
if ($null -eq $root) {
    throw 'AutomationElement.FromHandle returned null.'
}

$narrowStopwatch = [Diagnostics.Stopwatch]::StartNew()
$narrow = Get-UiaNarrowSemanticSample $root $MaxAncestryDepth
$narrowStopwatch.Stop()
$tabsStopwatch = [Diagnostics.Stopwatch]::StartNew()
$tabs = Find-UiaTabs $root $MaxTabElements $MaxTabChildren
$tabsStopwatch.Stop()
$benchmarkStopwatch = [Diagnostics.Stopwatch]::StartNew()
$benchmark = Measure-UiaNarrowPath (
    $root
) $BenchmarkIterations $MaxAncestryDepth

$snapshot = [ordered]@{
    Schema = 'shortcut_hud_wps_uia_probe_v1'
    CapturedAtUtc = [DateTime]::UtcNow.ToString('o')
    ForegroundHwnd = $foregroundHwnd.ToInt64()
    Root = Get-UiaElementRecord $root 0
    FocusedElement = $narrow.Focused
    ControlViewAncestry = $narrow.ControlAncestry
    RawViewAncestry = $narrow.RawAncestry
    Tabs = $tabs
    Benchmark = $benchmark
    Timing = [ordered]@{
        NarrowSampleMs = $narrowStopwatch.Elapsed.TotalMilliseconds
        TabScanMs = $tabsStopwatch.Elapsed.TotalMilliseconds
        BenchmarkMs = $benchmarkStopwatch.Elapsed.TotalMilliseconds
    }
    Notes = @(
        'Names, titles, and filename extensions are diagnostic only.',
        'No UIA pattern action is invoked by this probe.',
        'TextPattern2 and Legacy support are detected by UIA pattern ID.'
    )
}

$resolvedOutput = [IO.Path]::GetFullPath($Output)
$parent = Split-Path -Parent $resolvedOutput
if ($parent -and -not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
$snapshot | ConvertTo-Json -Depth 30 |
    Set-Content -LiteralPath $resolvedOutput -Encoding UTF8

[ordered]@{
    Output = $resolvedOutput
    ForegroundHwnd = $snapshot.ForegroundHwnd
    Root = $snapshot.Root
    FocusedElement = $snapshot.FocusedElement
    ControlViewReachedRoot = $snapshot.ControlViewAncestry.ReachedForegroundRoot
    RawViewReachedRoot = $snapshot.RawViewAncestry.ReachedForegroundRoot
    TabElementCount = $snapshot.Tabs.Items.Count
    TabScanStatus = $snapshot.Tabs.Status
    Benchmark = $snapshot.Benchmark
    Timing = $snapshot.Timing
} | ConvertTo-Json -Depth 12
