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
/// Что Scott помнит о своём человеке.
///
/// Раздел существует ради одного: память, которую нельзя увидеть и поправить,
/// — это не память, а слух. Человек сказал «запомни, что я работаю в вечернюю
/// смену»; Scott ответил «запомнил». Проверить это до сих пор было негде, а
/// забыть неверно понятое — тем более.
///
/// Запись отсюда и запись голосом ведут в одно место. Разойдись они, в списке
/// оказалось бы не всё, что Scott помнит, — и человек чинил бы ответы, глядя
/// на неполный список.
/// </summary>
public partial class MemoryViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    /// <summary>Всё, что помнит Scott, — до разбора по категориям.</summary>
    private readonly List<MemoryItem> _все = new();

    public ObservableCollection<MemoryItem> Visible { get; } = new();
    public ObservableCollection<MemoryKind> Kinds { get; } = new();

    /// <summary>Какая категория показана. Пусто — все сразу.</summary>
    [ObservableProperty] private string _activeKind = "";

    [ObservableProperty] private string _newText = "";
    [ObservableProperty] private string _newKind = "fact";
    [ObservableProperty] private bool _loading;
    [ObservableProperty] private string? _error;

    public bool IsEmpty => Visible.Count == 0 && !Loading;

    public MemoryViewModel(BackendClient client)
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
            var список = await _client.MemoriesAsync();

            if (список is null)
            {
                Error = "Backend не отвечает — память недоступна";
                return;
            }

            _все.Clear();
            _все.AddRange(список.Memories);

            Kinds.Clear();
            foreach (var вид in список.Kinds)
            {
                Kinds.Add(вид);
            }

            // Категория для новой записи: первая, если ничего не выбрано. Пустой
            // список в поле рядом с кнопкой «Запомнить» выглядит как незаполненное
            // обязательное поле, хотя выбор там всегда есть.
            if (Kinds.Count > 0 && !Kinds.Any(к => к.Id == NewKind))
            {
                NewKind = Kinds[0].Id;
            }

            ApplyFilter();
        }
        finally
        {
            Loading = false;
            OnPropertyChanged(nameof(IsEmpty));
        }
    }

    [RelayCommand]
    private void ShowKind(string? kind)
    {
        ActiveKind = kind ?? "";
        ApplyFilter();
    }

    private void ApplyFilter()
    {
        foreach (var вид in Kinds)
        {
            вид.IsActive = вид.Id == ActiveKind;
        }

        Visible.Clear();

        foreach (var запись in _все.Where(з => ActiveKind.Length == 0 || з.Kind == ActiveKind))
        {
            Visible.Add(запись);
        }

        OnPropertyChanged(nameof(IsEmpty));
    }

    [RelayCommand]
    private async Task Add()
    {
        var текст = (NewText ?? "").Trim();
        if (текст.Length == 0)
        {
            return;
        }

        var (успех, сообщение) = await _client.AddMemoryAsync(текст, NewKind);

        if (!успех)
        {
            ToastService.Error(сообщение.Length > 0 ? сообщение : "Не удалось запомнить");
            return;
        }

        // «Это Scott уже помнит» — не ошибка, но и не молчаливый успех: человек
        // должен понять, почему список не вырос.
        ToastService.Success(сообщение.Length > 0 ? сообщение : "Запомнил");

        NewText = "";
        await Refresh();
    }

    [RelayCommand]
    private async Task Forget(MemoryItem? запись)
    {
        if (запись is null)
        {
            return;
        }

        if (!await _client.ForgetMemoryAsync(запись.Id))
        {
            ToastService.Error("Не удалось забыть запись");
            return;
        }

        await Refresh();
    }

    [RelayCommand]
    private async Task ForgetAll()
    {
        // Спрашиваем подтверждение: это стирает всё, что Scott узнал о
        // человеке, и корзины здесь нет.
        var согласен = await DialogService.ConfirmAsync(
            "Забыть всё?",
            "Scott забудет всё, что вы просили запомнить. Восстановить это будет нельзя.",
            "Забыть");

        if (!согласен)
        {
            return;
        }

        if (!await _client.ForgetAllMemoriesAsync())
        {
            ToastService.Error("Не удалось очистить память");
            return;
        }

        ToastService.Success("Память очищена");
        await Refresh();
    }
}
