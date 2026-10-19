"""Windows UI Automation in an owned, bounded PowerShell process."""
import base64
import json
import os
from pathlib import Path
import subprocess

# User strings arrive ONLY through JSON stdin. No interpolation or eval.
SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    $failureCode='provider_unavailable'
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    # PowerShell hosts do not always register the standard Win32/MSAA proxies.
    # Modern providers still work if this optional framework assembly is absent.
    try {
        $providers = [Reflection.Assembly]::Load('UIAutomationClientsideProviders, Version=4.0.0.0, Culture=neutral, PublicKeyToken=31bf3856ad364e35')
        [System.Windows.Automation.ClientSettings]::RegisterClientSideProviderAssembly($providers.GetName())
    } catch { }
    $spec = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]::new([long]$spec.handle))
    if (!$root -or $root.Current.ProcessId -ne [int]$spec.pid) { throw 'Окно изменилось. Повторите выбор приложения.' }
    $cache = [System.Windows.Automation.CacheRequest]::new()
    foreach ($property in @('NameProperty','ControlTypeProperty','IsEnabledProperty','IsOffscreenProperty','IsPasswordProperty')) {
        $cache.Add([System.Windows.Automation.AutomationElement]::$property)
    }
    $cache.TreeScope = [System.Windows.Automation.TreeScope]::Element
    $cache.Push()
    try {
        $condition = [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::IsControlElementProperty, $true)
        $items = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
    } finally { $cache.Pop() }
    $names = [System.Collections.Generic.List[string]]::new()
    $matches = [System.Collections.Generic.List[object]]::new()
    $roles = @(50000,50002,50005,50007,50011,50013,50019)
    for ($i=0; $i -lt [Math]::Min($items.Count,1000); $i++) {
        $item = $items.Item($i)
        try {
            $info = $item.Cached
            if ($info.IsPassword -or !$info.IsEnabled -or $info.IsOffscreen -or $roles -notcontains $info.ControlType.Id) { continue }
            $label = $info.Name.Trim()
            if (!$label -or $label.Length -gt 160) { continue }
            if ($names.Count -lt 80 -and !$names.Contains($label)) { $names.Add($label) }
            if ($spec.operation -eq 'invoke' -and $label -ieq $spec.control.Trim()) { $matches.Add($item) }
        } catch { continue }
    }
    if ($spec.operation -eq 'controls') {
        @{success=$true;controls=@($names.ToArray());truncated=($items.Count -gt 1000)} | ConvertTo-Json -Compress -Depth 4
    } elseif ($spec.operation -eq 'invoke') {
        if ($matches.Count -eq 0) { $failureCode='no_control';throw 'Не нашёл доступную кнопку с таким названием. Попросите показать кнопки приложения.' }
        if ($matches.Count -ne 1) { $failureCode='ambiguous';throw 'Есть несколько одинаковых кнопок. Уточните окно или выберите кнопку вручную.' }
        $pattern = $null
        if (!$matches[0].TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) {
            $failureCode='no_pattern'
            throw 'Эта кнопка не предоставляет безопасное нажатие через UI Automation.'
        }
        # Re-check the window and process immediately before invoking.
        $again = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]::new([long]$spec.handle))
        if ($again.Current.ProcessId -ne [int]$spec.pid) { $failureCode='window_changed';throw 'Окно изменилось. Действие отменено.' }
        $failureCode='invoke_failed'
        $pattern.Invoke()
        @{success=$true;invoked=$true} | ConvertTo-Json -Compress
    } else { throw 'Неизвестное действие с кнопкой.' }
} catch {
    @{success=$false;code=$failureCode;message=([string]$_.Exception.Message).Substring(0,[Math]::Min(400,([string]$_.Exception.Message).Length))} | ConvertTo-Json -Compress
    exit 1
}
'''


def run(operation, window, control, environment):
    if os.name != 'nt':
        return dict(success=False, message='Нажатие кнопок через UI Automation пока доступно в Windows.')
    executable = Path(os.environ.get('SystemRoot', r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    encoded = base64.b64encode(SCRIPT.encode('utf-16-le')).decode('ascii')
    data = dict(operation=operation, handle=int(window['id'], 16), pid=window['pid'], control=control)
    try:
        result = subprocess.run([str(executable), '-NoProfile', '-NonInteractive', '-MTA', '-EncodedCommand', encoded],
            input=json.dumps(data).encode('utf-8'), capture_output=True, timeout=7, env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW)
        if len(result.stdout) > 262144:
            raise ValueError('Слишком большой ответ интерфейса приложения.')
        value = json.loads(result.stdout.decode('utf-8-sig'))
        if not isinstance(value, dict) or not isinstance(value.get('success'), bool):
            raise ValueError('Приложение не подтвердило доступ к элементам интерфейса.')
        return value
    except subprocess.TimeoutExpired:
        return dict(success=False, code='timeout', message='Приложение не ответило на запрос к интерфейсу. Повторное нажатие автоматически не отправлялось.')
    except (OSError, ValueError):
        return dict(success=False, message='Не удалось получить доступ к кнопкам приложения через UI Automation.')
