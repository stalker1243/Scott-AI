using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public partial class MacrosViewModel : ViewModelBase
{
    private readonly BackendClient _client;
    private readonly DispatcherTimer _statusTimer;

    public ObservableCollection<Macro> Macros { get; } = new();

    [ObservableProperty] private bool _loading;
    [ObservableProperty] private string? _error;

    [ObservableProperty] private bool _isRecording;
    [ObservableProperty] private string? _currentMacroName;
    [ObservableProperty] private int _actionsRecorded;
    [ObservableProperty] private string _newMacroName = "";

    [ObservableProperty] private string _actionType = "click";
    [ObservableProperty] private string _actionTarget = "";
    [ObservableProperty] private bool _busy;

    public string[] ActionTypes { get; } = { "click", "type", "wait", "command", "key_press", "open_app", "screenshot" };

    public MacrosViewModel(BackendClient client)
    {
        _client = client;
        _ = Refresh();

        // Первый запрос уходит, пока backend ещё поднимается, — тогда список
        // остаётся пустым. Повторяем, когда отвечать стало кому.
        BackendReady.WhenReady(() => _ = Refresh());
        _ = RefreshStatus();

        _statusTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2) };
        _statusTimer.Tick += async (_, _) => await RefreshStatus();
        _statusTimer.Start();
    }

    [RelayCommand]
    private async Task Refresh()
    {
        Loading = true;
        Error = null;
        try
        {
            var list = await _client.ListMacrosAsync();
            Macros.Clear();
            foreach (var m in list) Macros.Add(m);
        }
        catch (Exception ex)
        {
            Error = ex.Message;
        }
        finally
        {
            Loading = false;
        }
    }

    private async Task RefreshStatus()
    {
        try
        {
            var status = await _client.MacroStatusAsync();
            if (status is not null)
            {
                IsRecording = status.IsRecording;
                CurrentMacroName = status.CurrentMacro;
                ActionsRecorded = status.ActionsRecorded;
            }
        }
        catch
        {
            // backend недоступен — не трогаем текущее состояние
        }
    }

    [RelayCommand]
    private async Task StartRecording()
    {
        if (string.IsNullOrWhiteSpace(NewMacroName)) return;
        Busy = true;
        Error = null;
        try
        {
            var (success, message) = await _client.StartMacroRecordingAsync(NewMacroName.Trim());
            if (!success) { Error = message; ToastService.Error(message); return; }
            ToastService.Info($"Запись макроса «{NewMacroName.Trim()}» начата");
            NewMacroName = "";
            await RefreshStatus();
        }
        finally
        {
            Busy = false;
        }
    }

    [RelayCommand]
    private async Task StopRecording()
    {
        Busy = true;
        Error = null;
        try
        {
            var (success, message) = await _client.StopMacroRecordingAsync();
            if (!success) { Error = message; ToastService.Error(message); return; }
            ToastService.Success("Макрос сохранён");
            await RefreshStatus();
            await Refresh();
        }
        finally
        {
            Busy = false;
        }
    }

    [RelayCommand]
    private async Task AddAction()
    {
        if (string.IsNullOrWhiteSpace(ActionTarget) && ActionType != "screenshot") return;
        Busy = true;
        Error = null;
        try
        {
            var (success, message) = await _client.RecordMacroActionAsync(ActionType, ActionTarget.Trim());
            if (!success) { Error = message; return; }
            ActionTarget = "";
            await RefreshStatus();
        }
        finally
        {
            Busy = false;
        }
    }

    [RelayCommand]
    private async Task Execute(Macro macro)
    {
        Error = null;
        var (success, message) = await _client.ExecuteMacroAsync(macro.Name, macro.LoopCount);
        if (!success)
        {
            Error = message;
            ToastService.Error(message);
        }
        else
        {
            ToastService.Success($"Макрос «{macro.Name}» выполнен");
        }
    }

    [RelayCommand]
    private async Task Delete(Macro macro)
    {
        var confirmed = await DialogService.ConfirmAsync("Удалить макрос?", $"Макрос «{macro.Name}» будет удалён без возможности восстановления.");
        if (!confirmed) return;

        Error = null;
        var (success, message) = await _client.DeleteMacroAsync(macro.Name);
        if (!success) { Error = message; ToastService.Error(message); return; }
        ToastService.Success($"Макрос «{macro.Name}» удалён");
        await Refresh();
    }
}
