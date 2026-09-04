using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public partial class TemplatesViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    public ObservableCollection<ScottTemplate> Templates { get; } = new();

    [ObservableProperty] private bool _loading;
    [ObservableProperty] private string? _error;
    [ObservableProperty] private string? _status;
    [ObservableProperty] private bool _showForm;
    [ObservableProperty] private string _newName = "";
    [ObservableProperty] private string _newCategory = "custom";
    [ObservableProperty] private string _newDescription = "";
    [ObservableProperty] private string _newCommandsText = "";
    [ObservableProperty] private bool _saving;
    [ObservableProperty] private string? _applyingName;

    public TemplatesViewModel(BackendClient client)
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
            var list = await _client.ListTemplatesAsync();
            Templates.Clear();
            foreach (var t in list) Templates.Add(t);
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
    private async Task Create()
    {
        if (string.IsNullOrWhiteSpace(NewName) || string.IsNullOrWhiteSpace(NewCategory)) return;

        Saving = true;
        Error = null;
        try
        {
            var commands = NewCommandsText
                .Split('\n', System.StringSplitOptions.RemoveEmptyEntries | System.StringSplitOptions.TrimEntries)
                .ToList();

            var (success, message) = await _client.CreateTemplateAsync(NewName.Trim(), NewCategory.Trim(), NewDescription.Trim(), commands);
            if (!success) { Error = message; ToastService.Error(message); return; }
            ToastService.Success($"Шаблон «{NewName.Trim()}» создан");
            NewName = "";
            NewDescription = "";
            NewCommandsText = "";
            ShowForm = false;
            await Refresh();
        }
        finally
        {
            Saving = false;
        }
    }

    [RelayCommand]
    private async Task Delete(ScottTemplate template)
    {
        var confirmed = await DialogService.ConfirmAsync("Удалить шаблон?", $"Шаблон «{template.Name}» будет удалён без возможности восстановления.");
        if (!confirmed) return;

        Error = null;
        var (success, message) = await _client.DeleteTemplateAsync(template.Name);
        if (!success) { Error = message; ToastService.Error(message); return; }
        ToastService.Success($"Шаблон «{template.Name}» удалён");
        await Refresh();
    }

    [RelayCommand]
    private async Task Apply(ScottTemplate template)
    {
        ApplyingName = template.Name;
        Status = null;
        Error = null;
        try
        {
            var (success, message, applied) = await _client.ApplyTemplateAsync(template.Name);
            if (!success || applied is null)
            {
                Error = message;
                ToastService.Error(message);
                return;
            }

            var commandsRun = 0;
            foreach (var cmd in applied.Commands)
            {
                try
                {
                    await _client.RunCommandAsync(cmd);
                    commandsRun++;
                }
                catch
                {
                    // одна неудачная команда не должна останавливать остальной шаблон
                }
            }

            var rulesCreated = 0;
            foreach (var rule in applied.Rules)
            {
                if (rule.Conditions.Count == 0) continue;
                var cond = rule.Conditions[0];
                var (ruleSuccess, _) = await _client.AddIftttRuleAsync(rule.Name, cond.TriggerType, cond.TriggerValue, rule.ActionType, rule.ActionValue, "");
                if (ruleSuccess) rulesCreated++;
            }

            Status = $"Шаблон «{template.Name}» применён: выполнено команд — {commandsRun}, создано правил — {rulesCreated}.";
            ToastService.Success($"Шаблон «{template.Name}» применён");
            await Refresh();
        }
        finally
        {
            ApplyingName = null;
        }
    }
}
