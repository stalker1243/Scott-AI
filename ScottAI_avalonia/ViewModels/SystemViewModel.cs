using System.Collections.ObjectModel;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public partial class SystemViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    public ObservableCollection<ProcessInfo> Processes { get; } = new();

    [ObservableProperty]
    private bool _loading;

    [ObservableProperty]
    private string? _error;

    public SystemViewModel(BackendClient client)
    {
        _client = client;
        _ = Refresh();
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
