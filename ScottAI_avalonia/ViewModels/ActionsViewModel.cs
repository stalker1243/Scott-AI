using System.Collections.ObjectModel;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>
/// Что Scott умеет.
///
/// До сих пор узнать это было негде: четыре случайных примера на главной
/// странице создавали впечатление, что он умеет ровно четыре вещи. Голосовой
/// помощник, возможности которого угадывают, используется на десятую часть.
///
/// Примеры фраз здесь нажимаются: прочитать, как просить, мало — надо
/// попробовать и увидеть, что получилось.
/// </summary>
public partial class ActionsViewModel : ViewModelBase
{
    private readonly BackendClient _client;
    private readonly System.Action<string> _askScott;

    public ObservableCollection<AbilityGroup> Groups { get; } = new();

    [ObservableProperty] private string _summary = "";
    [ObservableProperty] private bool _loading;
    [ObservableProperty] private string? _error;

    public ActionsViewModel(BackendClient client, System.Action<string> askScott)
    {
        _client = client;
        _askScott = askScott;
    }

    [RelayCommand]
    public async Task Refresh()
    {
        Loading = true;
        Error = null;

        try
        {
            var ответ = await _client.AbilitiesAsync();

            if (ответ is null)
            {
                Error = "Backend не отвечает — список умений недоступен";
                return;
            }

            Groups.Clear();
            foreach (var группа in ответ.Groups)
            {
                Groups.Add(группа);
            }

            Summary = ответ.Ready == ответ.Total
                ? $"Доступно всё: {ответ.Total}"
                : $"Доступно {ответ.Ready} из {ответ.Total}";
        }
        finally
        {
            Loading = false;
        }
    }

    /// <summary>
    /// Попробовать пример прямо отсюда.
    ///
    /// Уходит в чат, а не выполняется молча: человек должен увидеть, что Scott
    /// ответил, — иначе непонятно, сработало ли и что именно случилось.
    /// </summary>
    [RelayCommand]
    private void Try(string? фраза)
    {
        if (!string.IsNullOrWhiteSpace(фраза))
        {
            _askScott(фраза);
        }
    }
}
