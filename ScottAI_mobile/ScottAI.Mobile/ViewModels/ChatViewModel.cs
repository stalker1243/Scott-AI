using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Mobile.Models;
using ScottAI.Mobile.Services;

namespace ScottAI.Mobile.ViewModels;

/// <summary>
/// Разговор со Scott с телефона.
///
/// Это не чат с ИИ, хотя выглядит так же. Всё, что здесь пишут, выполняется на
/// домашнем компьютере — в комнате, где никого нет. Отсюда две особенности,
/// которых не бывает в обычных чатах: отказ показывается как полноценный ответ
/// (издалека Scott делает не всё, что умеет вообще), а обрыв связи — как явная
/// неудача, потому что команда могла не дойти.
/// </summary>
public partial class ChatViewModel : ViewModelBase
{
    private readonly ScottClient _client;

    public ObservableCollection<ChatMessage> Messages { get; } = new();

    [ObservableProperty] private string _input = "";
    [ObservableProperty] private bool _busy;

    public bool Empty => Messages.Count == 0;
    public bool Paired => SettingsStore.Current.Paired;

    public ChatViewModel(ScottClient client)
    {
        _client = client;

        // Показать пример переписки — для проверки внешнего вида в окне на
        // компьютере. Без этого вид реплик не проверить вовсе: чтобы они
        // появились, нужен привязанный телефон и живой компьютер, а нажать
        // кнопку в окне со стороны нельзя. На телефоне переменной нет.
        if (Environment.GetEnvironmentVariable("SCOTT_DEMO") == "1")
        {
            Messages.Add(new ChatMessage { Text = "открой браузер", Mine = true });
            Messages.Add(new ChatMessage { Text = "Открыл Chrome." });
            Messages.Add(new ChatMessage { Text = "выключи компьютер", Mine = true });
            Messages.Add(new ChatMessage
            {
                Text = "Выключение компьютера издалека я не делаю — вдруг на нём идёт работа.",
                Refused = true,
            });
            Messages.Add(new ChatMessage
            {
                Text = "напомни через час про созвон",
                Mine = true,
            });
            Messages.Add(new ChatMessage
            {
                Text = "Связи с компьютером нет: он мог уснуть или выйти из сети.",
                Failed = true,
            });
        }
    }

    [RelayCommand]
    private async Task Send()
    {
        var текст = (Input ?? "").Trim();
        if (текст.Length == 0 || Busy)
        {
            return;
        }

        Messages.Add(new ChatMessage { Text = текст, Mine = true });
        OnPropertyChanged(nameof(Empty));

        // Поле очищается сразу: человек уже нажал, и оставлять текст на месте
        // значит подталкивать его отправить то же самое второй раз.
        Input = "";
        Busy = true;

        try
        {
            var итог = await _client.SendAsync(текст);

            Messages.Add(new ChatMessage
            {
                Text = итог.Text,
                Refused = итог.Refused,
                Failed = итог.Failed,
            });
        }
        finally
        {
            Busy = false;
        }
    }

    /// <summary>Подсказки для пустого чата — то, что издалека точно разрешено.</summary>
    public string[] Hints { get; } =
    {
        "открой браузер",
        "что у меня с диском",
        "напомни через час про созвон",
        "открой проект ScottAI",
    };

    [RelayCommand]
    private async Task UseHint(string? подсказка)
    {
        if (подсказка is null)
        {
            return;
        }

        Input = подсказка;
        await Send();
    }

    /// <summary>
    /// Забыть переписку.
    ///
    /// История живёт только в памяти и на диск не попадает: команды к домашнему
    /// компьютеру — не та переписка, которую стоит хранить в телефоне, который
    /// теряют.
    /// </summary>
    [RelayCommand]
    private void Clear()
    {
        Messages.Clear();
        OnPropertyChanged(nameof(Empty));
    }

    public void NotifyPairingChanged() => OnPropertyChanged(nameof(Paired));
}
