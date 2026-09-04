using System;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public partial class HomeViewModel : ViewModelBase
{
    private readonly BackendClient _client;
    private readonly Action _onLaunchChat;
    private readonly DispatcherTimer _animTimer;

    private double _cpuTarget;
    private double _ramTarget;
    private double _processTarget;
    private double _processDisplay;

    [ObservableProperty]
    private double _cpuPercent;

    [ObservableProperty]
    private double _ramPercent;

    [ObservableProperty]
    private int _processCount;

    public HomeViewModel(BackendClient client, Action onLaunchChat)
    {
        _client = client;
        _onLaunchChat = onLaunchChat;

        // Плавный "подъезд" чисел к новому значению вместо резкой смены на каждый
        // опрос метрик — 20 кадров/сек достаточно для лёгкого ease-towards-target
        // без заметной нагрузки на UI-поток.
        _animTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(50) };
        _animTimer.Tick += (_, _) => TickAnimation();
        _animTimer.Start();

        _ = PollMetricsAsync();
    }

    private void TickAnimation()
    {
        const double ease = 0.22;
        CpuPercent = Ease(CpuPercent, _cpuTarget, ease);
        RamPercent = Ease(RamPercent, _ramTarget, ease);
        _processDisplay = Ease(_processDisplay, _processTarget, ease);
        ProcessCount = (int)Math.Round(_processDisplay);
    }

    private static double Ease(double current, double target, double factor)
    {
        var diff = target - current;
        if (Math.Abs(diff) < 0.05) return target;
        return current + diff * factor;
    }

    private async System.Threading.Tasks.Task PollMetricsAsync()
    {
        while (true)
        {
            var metrics = await _client.MetricsAsync();
            if (metrics?.Metrics is not null)
            {
                _cpuTarget = metrics.Metrics.Cpu;
                _ramTarget = metrics.Metrics.Ram;
                _processTarget = metrics.Metrics.Processes;
            }
            await System.Threading.Tasks.Task.Delay(TimeSpan.FromSeconds(3));
        }
    }

    [RelayCommand]
    private void LaunchChat() => _onLaunchChat();
}
