using System.Collections.ObjectModel;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>
/// Проекты, над которыми человек работает.
///
/// Список сам по себе бесполезен — такой заводят в блокноте. Польза в том, что
/// им пользуется Scott: открывает папку по названию («открой проект ScottAI») и
/// держит текущий проект в уме, отвечая на вопросы о работе. Человеку,
/// пишущему на C#, ответ про C# полезнее ответа вообще — и повторять это в
/// каждом вопросе он больше не должен.
/// </summary>
public partial class ProjectsViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    public ObservableCollection<Project> Projects { get; } = new();

    [ObservableProperty] private bool _loading;
    [ObservableProperty] private string? _error;

    // ---- Новый проект ----
    [ObservableProperty] private bool _adding;
    [ObservableProperty] private string _newName = "";
    [ObservableProperty] private string _newPath = "";
    [ObservableProperty] private string _newStack = "";
    [ObservableProperty] private string _newNote = "";

    public bool IsEmpty => Projects.Count == 0 && !Loading;

    public ProjectsViewModel(BackendClient client)
    {
        _client = client;
    }

    [RelayCommand]
    public async Task Refresh()
    {
        Loading = true;
        Error = null;

        try
        {
            var список = await _client.ProjectsAsync();

            Projects.Clear();
            foreach (var проект in список)
            {
                Projects.Add(проект);
            }
        }
        finally
        {
            Loading = false;
            OnPropertyChanged(nameof(IsEmpty));
        }
    }

    [RelayCommand]
    private void StartAdding() => Adding = true;

    [RelayCommand]
    private void CancelAdding()
    {
        Adding = false;
        NewName = NewPath = NewStack = NewNote = "";
    }

    [RelayCommand]
    private async Task Add()
    {
        var имя = (NewName ?? "").Trim();
        if (имя.Length == 0)
        {
            ToastService.Error("У проекта должно быть название");
            return;
        }

        var (успех, сообщение) = await _client.AddProjectAsync(
            имя, (NewPath ?? "").Trim(), (NewStack ?? "").Trim(), (NewNote ?? "").Trim());

        if (!успех)
        {
            ToastService.Error(сообщение.Length > 0 ? сообщение : "Не удалось завести проект");
            return;
        }

        // Папки может ещё не быть — это не отказ, но человек должен узнать
        // сразу, а не при первой попытке открыть.
        if (сообщение.Length > 0)
        {
            ToastService.Error(сообщение);
        }
        else
        {
            ToastService.Success($"Проект «{имя}» заведён");
        }

        CancelAdding();
        await Refresh();
    }

    [RelayCommand]
    private async Task Open(Project? проект)
    {
        if (проект is null)
        {
            return;
        }

        var (успех, сообщение) = await _client.OpenProjectAsync(проект.Id);

        if (!успех)
        {
            ToastService.Error(сообщение.Length > 0 ? сообщение : "Не удалось открыть папку");
            return;
        }

        // Раз открыли — над ним и работают: список перечитываем, чтобы отметка
        // «текущий» переехала сразу.
        await Refresh();
    }

    [RelayCommand]
    private async Task MakeCurrent(Project? проект)
    {
        if (проект is null || проект.Current)
        {
            return;
        }

        if (!await _client.SetCurrentProjectAsync(проект.Id))
        {
            ToastService.Error("Не удалось переключиться");
            return;
        }

        ToastService.Success($"Scott будет держать в уме «{проект.Name}»");
        await Refresh();
    }

    [RelayCommand]
    private async Task Forget(Project? проект)
    {
        if (проект is null)
        {
            return;
        }

        // Спрашиваем, но объясняем и то, чего НЕ случится: папка с работой
        // останется на месте. Иначе человек побоится нажать.
        var согласен = await DialogService.ConfirmAsync(
            $"Забыть проект «{проект.Name}»?",
            "Scott перестанет о нём знать. Папка с работой останется на месте — она не удаляется.",
            "Забыть");

        if (!согласен)
        {
            return;
        }

        if (!await _client.ForgetProjectAsync(проект.Id))
        {
            ToastService.Error("Не удалось забыть проект");
            return;
        }

        await Refresh();
    }
}
