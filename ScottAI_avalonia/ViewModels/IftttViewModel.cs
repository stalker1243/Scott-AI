using System.Collections.ObjectModel;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public partial class IftttViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    public ObservableCollection<IftttRule> Rules { get; } = new();

    [ObservableProperty] private bool _loading;
    [ObservableProperty] private string? _error;
    [ObservableProperty] private bool _showForm;
    [ObservableProperty] private string _newName = "";
    [ObservableProperty] private string _newTriggerType = "command_contains";
    [ObservableProperty] private string _newTriggerValue = "";
    [ObservableProperty] private string _newActionType = "execute_command";
    [ObservableProperty] private string _newActionValue = "";
    [ObservableProperty] private string _newDescription = "";
    [ObservableProperty] private bool _saving;

    public string[] TriggerTypes { get; } = { "command_contains", "command_equals", "app_opened", "time" };
    public string[] ActionTypes { get; } = { "execute_command", "open_app", "send_notification", "send_message", "run_script", "custom_action" };

    public IftttViewModel(BackendClient client)
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
            var list = await _client.ListIftttRulesAsync();
            Rules.Clear();
            foreach (var r in list) Rules.Add(r);
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
        if (string.IsNullOrWhiteSpace(NewName) || string.IsNullOrWhiteSpace(NewTriggerValue) || string.IsNullOrWhiteSpace(NewActionValue))
            return;

        Saving = true;
        Error = null;
        try
        {
            var (success, message) = await _client.AddIftttRuleAsync(NewName.Trim(), NewTriggerType, NewTriggerValue.Trim(), NewActionType, NewActionValue.Trim(), NewDescription.Trim());
            if (!success)
            {
                Error = message;
                ToastService.Error(message);
                return;
            }
            ToastService.Success($"Правило «{NewName.Trim()}» добавлено");
            NewName = "";
            NewTriggerValue = "";
            NewActionValue = "";
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
    private async Task Delete(IftttRule rule)
    {
        var confirmed = await DialogService.ConfirmAsync("Удалить правило?", $"Правило «{rule.Name}» будет удалено без возможности восстановления.");
        if (!confirmed) return;

        Error = null;
        var (success, message) = await _client.DeleteIftttRuleAsync(rule.Name);
        if (!success)
        {
            Error = message;
            ToastService.Error(message);
            return;
        }
        ToastService.Success($"Правило «{rule.Name}» удалено");
        await Refresh();
    }
}
