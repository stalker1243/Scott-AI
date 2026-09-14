using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public partial class SystemViewModel : ViewModelBase
{
    private readonly BackendClient _client;
    private readonly DispatcherTimer _animTimer;

    // Куда числам ехать. Показываемое значение догоняет замеренное плавно:
    // резкие скачки на каждом опросе читаются как мигание, а не как нагрузка.
    private double _cpuTarget;
    private double _ramTarget;
    private double _gpuTarget;
    private double _diskTarget;
    private double _processTarget;
    private double _processDisplay;

    public ObservableCollection<ProcessInfo> Processes { get; } = new();

    // ---- Нагрузка машины ----
    //
    // Раньше эти числа жили на главной странице и питали голограмму. Там они
    // отвечали на вопрос, которого при запуске помощника никто не задаёт;
    // здесь, в разделе «Система», они и есть предмет разговора.

    [ObservableProperty] private double _cpuPercent;
    [ObservableProperty] private double _ramPercent;
    [ObservableProperty] private int _processCount;

    /// <summary>Загрузка видеокарты. Ноль означает и «свободна», и «её нет».</summary>
    [ObservableProperty] private double _gpuPercent;

    /// <summary>Нагрузка на диск — доля времени, когда он был занят работой.</summary>
    [ObservableProperty] private double _diskPercent;

    /// <summary>
    /// Сколько места на диске занято.
    ///
    /// Величина медленная: она меняется не в такт остальным и плавного
    /// подъезда к новому значению не требует, поэтому берётся как есть.
    /// </summary>
    [ObservableProperty] private double _diskUsagePercent;

    [ObservableProperty]
    private bool _loading;

    [ObservableProperty]
    private string? _error;

    public SystemViewModel(BackendClient client)
    {
        _client = client;

        // Двадцать кадров в секунду: достаточно, чтобы движение читалось
        // плавным, и незаметно для UI-потока.
        _animTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(50) };
        _animTimer.Tick += (_, _) => TickAnimation();
        _animTimer.Start();

        _ = PollMetricsAsync();
        _ = Refresh();

        // Первый запрос уходит, пока backend ещё поднимается, — тогда список
        // остаётся пустым. Повторяем, когда отвечать стало кому.
        BackendReady.WhenReady(() => _ = Refresh());
    }

    [RelayCommand]
    private async Task Refresh()
    {
        Loading = true;
        Error = null;
        try
        {
            var list = await _client.ListProcessesAsync();
            Processes.Clear();
            foreach (var p in list) Processes.Add(p);
        }
        catch (System.Exception ex)
        {
            Error = ex.Message;
        }
        finally
        {
            Loading = false;
        }
    }

    private async Task PollMetricsAsync()
    {
        while (true)
        {
            var metrics = await _client.MetricsAsync();
            if (metrics?.Metrics is not null)
            {
                _cpuTarget = metrics.Metrics.Cpu;
                _ramTarget = metrics.Metrics.Ram;
                _gpuTarget = metrics.Metrics.Gpu;
                _diskTarget = metrics.Metrics.Disk;
                DiskUsagePercent = metrics.Metrics.DiskUsage;
                _processTarget = metrics.Metrics.Processes;
            }

            await Task.Delay(TimeSpan.FromSeconds(3));
        }
    }

    private void TickAnimation()
    {
        const double ease = 0.22;
        CpuPercent = Ease(CpuPercent, _cpuTarget, ease);
        RamPercent = Ease(RamPercent, _ramTarget, ease);
        GpuPercent = Ease(GpuPercent, _gpuTarget, ease);
        DiskPercent = Ease(DiskPercent, _diskTarget, ease);
        _processDisplay = Ease(_processDisplay, _processTarget, ease);
        ProcessCount = (int)System.Math.Round(_processDisplay);
    }

    private static double Ease(double current, double target, double factor)
    {
        var diff = target - current;
        if (System.Math.Abs(diff) < 0.05) return target;
        return current + diff * factor;
    }

    [RelayCommand]
    private async Task Kill(ProcessInfo process)
    {
        var confirmed = await DialogService.ConfirmAsync(
            "Завершить процесс?",
            $"Процесс «{process.Name}» (PID {process.Pid}) будет принудительно завершён. Несохранённые данные в нём будут потеряны.",
            "Завершить");
        if (!confirmed) return;

        Error = null;
        var (success, message) = await _client.KillProcessAsync(process.Pid);
        if (!success)
        {
            Error = message;
            ToastService.Error(message);
            return;
        }
        ToastService.Success($"Процесс «{process.Name}» завершён");
        await Refresh();
    }
}
