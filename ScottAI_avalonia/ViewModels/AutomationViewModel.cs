using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>Контейнер вкладки «Автоматизация» — переключает под-разделы.</summary>
public partial class AutomationViewModel : ViewModelBase
{
    public CustomCommandsViewModel Commands { get; }
    public IftttViewModel Ifttt { get; }
    public MacrosViewModel Macros { get; }
    public TemplatesViewModel Templates { get; }
    public ProtocolsViewModel Protocols { get; }

    [ObservableProperty]
    private ViewModelBase _currentTab;

    [ObservableProperty]
    private string _activeTab = "protocols";

    public AutomationViewModel(BackendClient client)
    {
        Commands = new CustomCommandsViewModel(client);
        Ifttt = new IftttViewModel(client);
        Macros = new MacrosViewModel(client);
        Templates = new TemplatesViewModel(client);
        Protocols = new ProtocolsViewModel(client);

        // Протоколы открываются первыми: это единственный раздел, где одна
        // запись делает несколько дел подряд, и с него понятнее всего, зачем
        // страница нужна.
        _currentTab = Protocols;
    }

    [RelayCommand]
    private void ShowProtocols()
    {
        CurrentTab = Protocols;
        ActiveTab = "protocols";

        // Список перечитывается при каждом открытии, а не только при создании
        // модели. Протокол можно завести и голосом, и из другого места — без
        // этого он не появлялся бы в списке до перезапуска лаунчера.
        Protocols.RefreshCommand.Execute(null);
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
