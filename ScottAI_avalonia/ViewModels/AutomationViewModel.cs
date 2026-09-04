using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>Контейнер вкладки «Автоматизация» — переключает 4 под-раздела (как в Tauri-версии).</summary>
public partial class AutomationViewModel : ViewModelBase
{
    public CustomCommandsViewModel Commands { get; }
    public IftttViewModel Ifttt { get; }
    public MacrosViewModel Macros { get; }
    public TemplatesViewModel Templates { get; }

    [ObservableProperty]
    private ViewModelBase _currentTab;

    [ObservableProperty]
    private string _activeTab = "commands";

    public AutomationViewModel(BackendClient client)
    {
        Commands = new CustomCommandsViewModel(client);
        Ifttt = new IftttViewModel(client);
        Macros = new MacrosViewModel(client);
        Templates = new TemplatesViewModel(client);
        _currentTab = Commands;
    }

    [RelayCommand]
    private void ShowCommands()
    {
        CurrentTab = Commands;
        ActiveTab = "commands";
    }

    [RelayCommand]
    private void ShowIfttt()
    {
        CurrentTab = Ifttt;
        ActiveTab = "ifttt";
    }

    [RelayCommand]
    private void ShowMacros()
    {
        CurrentTab = Macros;
        ActiveTab = "macros";
    }

    [RelayCommand]
    private void ShowTemplates()
    {
        CurrentTab = Templates;
        ActiveTab = "templates";
    }
}
