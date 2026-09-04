using System.Collections.ObjectModel;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public partial class CustomCommandsViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    public ObservableCollection<CustomCommand> Commands { get; } = new();

    [ObservableProperty]
    private bool _loading;

    [ObservableProperty]
    private string? _error;

    [ObservableProperty]
    private bool _showForm;

    [ObservableProperty]
    private string _newName = "";

    [ObservableProperty]
    private string _newTrigger = "";

    [ObservableProperty]
    private string _newAction = "";

    [ObservableProperty]
    private string _newDescription = "";

    [ObservableProperty]
    private bool _saving;

    public CustomCommandsViewModel(BackendClient client)
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
            var list = await _client.ListCustomCommandsAsync();
            Commands.Clear();
            foreach (var c in list) Commands.Add(c);
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
    private void ToggleForm() => ShowForm = !ShowForm;

    [RelayCommand]
    private async Task Add()
    {
        if (string.IsNullOrWhiteSpace(NewName) || string.IsNullOrWhiteSpace(NewTrigger) || string.IsNullOrWhiteSpace(NewAction))
            return;

        Saving = true;
        Error = null;
        try
        {
            var (success, message) = await _client.AddCustomCommandAsync(NewName.Trim(), NewTrigger.Trim(), NewAction.Trim(), NewDescription.Trim());
            if (!success)
            {
                Error = message;
                ToastService.Error(message);
                return;
            }
            ToastService.Success($"Команда «{NewName.Trim()}» добавлена");
            NewName = "";
            NewTrigger = "";
            NewAction = "";
            NewDescription = "";
            ShowForm = false;
            await Refresh();
        }
        finally
        {
            Saving = false;
        }
    }

    [RelayCommand]
    private async Task Delete(CustomCommand command)
    {
        var confirmed = await DialogService.ConfirmAsync("Удалить команду?", $"Команда «{command.Name}» будет удалена без возможности восстановления.");
        if (!confirmed) return;

        Error = null;
        var (success, message) = await _client.DeleteCustomCommandAsync(command.Name);
        if (!success)
        {
            Error = message;
            ToastService.Error(message);
            return;
        }
        ToastService.Success($"Команда «{command.Name}» удалена");
        await Refresh();
    }
}
