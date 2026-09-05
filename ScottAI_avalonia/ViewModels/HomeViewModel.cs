using System;
using System.Threading.Tasks;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
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

    // ---- Прослушивание микрофона ----
    // Scott слушает непрерывно, но выполняет только то, что сказано после его
    // имени. Поэтому счётчиков два: сколько фраз он услышал вообще и сколько
    // из них были обращены к нему — по разнице сразу видно, слышит ли он
    // комнату и узнаёт ли себя.
    [ObservableProperty] private bool _isListening;
    [ObservableProperty] private bool _micAvailable = true;
    [ObservableProperty] private bool _listenBusy;
    [ObservableProperty] private string _listenHint = "Scott не слушает";
    [ObservableProperty] private string _lastHeard = "";

    public string ListenButtonText => IsListening ? "Не слушать" : "Слушать";

    partial void OnIsListeningChanged(bool value) => OnPropertyChanged(nameof(ListenButtonText));

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
        _ = RefreshListening();
    }

    [RelayCommand]
    private async Task ToggleListening()
    {
        ListenBusy = true;
        try
        {
            var (success, message, state) = await _client.SetListeningAsync(!IsListening);
            if (!success)
            {
                ListenHint = message;
                ToastService.Error(message);
                return;
            }

            ApplyListenState(state);
            ToastService.Success(IsListening ? "Scott слушает — обратитесь к нему по имени" : "Scott больше не слушает");
        }
        finally
        {
            ListenBusy = false;
        }
    }

    [RelayCommand]
    private async Task RefreshListening()
    {
        ApplyListenState(await _client.ListenStatusAsync());
    }

    private void ApplyListenState(ListenStatus? state)
    {
        if (state is null)
        {
            IsListening = false;
            ListenHint = "backend не отвечает";
            return;
        }

        IsListening = state.Listening;
        MicAvailable = state.Available;
        LastHeard = state.LastText;

        if (!state.Available)
        {
            ListenHint = "Записывать звук нечем: не установлена библиотека sounddevice";
        }
        else if (!state.Listening)
        {
            ListenHint = "Scott не слушает";
        }
        else
        {
            // Показываем обе цифры: если фразы слышны, а обращений нет — значит
            // Scott не узнаёт своё имя, и это совсем другая проблема, чем
            // «микрофон не слышит».
            ListenHint = $"Слушаю. Услышано фраз: {state.PhrasesHeard}, из них ко мне: {state.Triggered}";
        }
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
