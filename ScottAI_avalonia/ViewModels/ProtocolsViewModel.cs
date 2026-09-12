using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>
/// Протоколы: именованные последовательности шагов.
///
/// Шаги человек пишет теми же словами, какими сказал бы их голосом, по одному
/// на строку. Это не упрощение формы ради экономии: так протоколу достаётся
/// весь разбор, уже отлаженный на сотнях фраз, и составителю не нужно знать ни
/// одного названия действия. Форма с выпадающими списками действий и полями
/// параметров — как у IFTTT-правил — заставила бы учить их все.
/// </summary>
public partial class ProtocolsViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    public ObservableCollection<Protocol> Protocols { get; } = new();

    [ObservableProperty] private bool _loading;
    [ObservableProperty] private string? _error;
    [ObservableProperty] private bool _showForm;
    [ObservableProperty] private string _newName = "";
    [ObservableProperty] private string _newSteps = "";
    [ObservableProperty] private string _newPhrases = "";
    [ObservableProperty] private string _newDescription = "";
    [ObservableProperty] private bool _saving;

    /// <summary>Какой протокол сейчас выполняется — по нему гаснут кнопки запуска.</summary>
    [ObservableProperty] private string? _running;

    public ProtocolsViewModel(BackendClient client)
    {
        _client = client;
        _ = Refresh();

        // Первый запрос уходит, пока backend ещё поднимается, — тогда список
        // остаётся пустым. Повторяем, когда отвечать стало кому.
        BackendReady.WhenReady(() => _ = Refresh());
    }

    [RelayCommand]
    private async Task Refresh()
    {
        Loading = true;
        Error = null;
        try
        {
            var list = await _client.ListProtocolsAsync();
            Protocols.Clear();
            foreach (var item in list) Protocols.Add(item);
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
        var steps = SplitLines(NewSteps)
            .Select(line => new ProtocolStep { Text = line })
            .ToList();

        if (string.IsNullOrWhiteSpace(NewName) || steps.Count == 0)
        {
            Error = "Нужно имя и хотя бы один шаг";
            return;
        }

        Saving = true;
        Error = null;
        try
        {
            var (success, message) = await _client.AddProtocolAsync(
                NewName.Trim(), steps, SplitLines(NewPhrases), NewDescription.Trim());

            if (!success)
            {
                Error = message;
                ToastService.Error(message);
                return;
            }

            ToastService.Success($"Протокол «{NewName.Trim()}» создан");
            NewName = "";
            NewSteps = "";
            NewPhrases = "";
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
    private async Task Run(Protocol protocol)
    {
        Running = protocol.Name;
        Error = null;
        try
        {
            var (success, message) = await _client.RunProtocolAsync(protocol.Name);

            if (success) ToastService.Success(message);
            else ToastService.Error(message);

            // Счётчик запусков меняется на стороне backend — список нужно
            // перечитать, иначе он останется прежним до перехода по вкладкам.
            await Refresh();
        }
        catch (System.Exception ex)
        {
            Error = ex.Message;
            ToastService.Error(ex.Message);
        }
        finally
        {
            Running = null;
        }
    }

    [RelayCommand]
    private async Task Delete(Protocol protocol)
    {
        var confirmed = await DialogService.ConfirmAsync(
            "Удалить протокол?",
            $"Протокол «{protocol.Name}» будет удалён без возможности восстановления.");

        if (!confirmed) return;

        Error = null;
        var (success, message) = await _client.DeleteProtocolAsync(protocol.Name);

        if (!success)
        {
            Error = message;
            ToastService.Error(message);
            return;
        }

        ToastService.Success($"Протокол «{protocol.Name}» удалён");
        await Refresh();
    }

    /// <summary>
    /// Разбить текст на непустые строки.
    ///
    /// Человек, набирая список, оставляет пустые строки между смысловыми
    /// кусками и пробелы в конце. Превращать их в шаги нельзя: пустой шаг
    /// разбирать нечего, и протокол на нём остановится.
    /// </summary>
    private static List<string> SplitLines(string text) =>
        (text ?? "")
        .Replace("\r\n", "\n")
        .Split('\n')
        .Select(line => line.Trim())
        .Where(line => line.Length > 0)
        .ToList();
}
