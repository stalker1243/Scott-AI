using System;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Mobile.Services;

namespace ScottAI.Mobile.ViewModels;

/// <summary>
/// Три экрана и переключение между ними.
///
/// Вкладки внизу, а не сбоку: на телефоне до верха экрана большой палец не
/// достаёт, а держат его обычно одной рукой.
///
/// Экранов ровно три, и это осознанно мало. Приложение — не второй лаунчер:
/// всё, что настраивают редко, остаётся на компьютере, где есть мышь и место.
/// Здесь только то, чем пользуются на ходу.
/// </summary>
public partial class MainViewModel : ViewModelBase
{
    public ChatViewModel Chat { get; }
    public SyncViewModel Sync { get; }
    public AppearanceViewModel Appearance { get; }

    /// <summary>Открытый экран: chat | look | sync.</summary>
    [ObservableProperty] private string _tab = "chat";

    /// <summary>
    /// Связан ли телефон с компьютером — видно в шапке на каждом экране.
    ///
    /// Иначе о непривязанности узнаёшь только по ответу на первую команду, а к
    /// тому времени человек уже успел на неё рассчитывать.
    /// </summary>
    public bool Linked => SettingsStore.Current.Paired;

    public string StateText => Linked
        ? SettingsStore.Current.Host
        : "телефон не привязан";

    public bool OnChat => Tab == "chat";
    public bool OnLook => Tab == "look";
    public bool OnSync => Tab == "sync";

    public MainViewModel()
    {
        var клиент = new ScottClient();

        Chat = new ChatViewModel(клиент);
        Sync = new SyncViewModel(клиент);
        Appearance = new AppearanceViewModel();

        // Чат должен узнать о привязке сразу: пока её нет, он показывает не
        // подсказки, а объяснение, куда идти.
        Sync.PairingChanged = () =>
        {
            Chat.NotifyPairingChanged();

            // Шапка показывает состояние связи на каждом экране, и обновиться
            // она должна в тот же миг, а не при следующем переключении вкладки.
            OnPropertyChanged(nameof(Linked));
            OnPropertyChanged(nameof(StateText));
        };

        // Непривязанный телефон открывается на «Связи»: чат ему всё равно
        // ответит только «сначала привяжитесь».
        if (!SettingsStore.Current.Paired)
        {
            Tab = "sync";
        }

        // Открыть нужный экран сразу — для отладки в окне на компьютере.
        // Приложение проверяют снимками экрана, а нажать в нём кнопку со
        // стороны нельзя: без этого каждый взгляд на «Вид» стоил правки в
        // коде и пересборки. На телефоне переменной нет, и строка не
        // делает ничего.
        var начальная = Environment.GetEnvironmentVariable("SCOTT_START_TAB");
        if (начальная is "chat" or "look" or "sync")
        {
            Tab = начальная;
        }
    }

    partial void OnTabChanged(string value)
    {
        OnPropertyChanged(nameof(OnChat));
        OnPropertyChanged(nameof(OnLook));
        OnPropertyChanged(nameof(OnSync));
    }

    [RelayCommand]
    private void Open(string? вкладка)
    {
        if (вкладка is not null)
        {
            Tab = вкладка;
        }
    }
}
