using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Mobile.Services;

namespace ScottAI.Mobile.ViewModels;

/// <summary>
/// Связь с компьютером.
///
/// ПОЧЕМУ ПРИВЯЗКА ИДЁТ КОДОМ С ЭКРАНА. Это единственное доказательство, что
/// привязывающий стоит у самого компьютера. Пароль можно подсмотреть, адрес в
/// сети виден соседям, а код живёт минуту и годится один раз.
///
/// Приложение хранит только выданный ключ. Показать его повторно компьютер не
/// может — в списке устройств ключа нет, — поэтому «забыл ключ» здесь означает
/// привязку заново, и это правильная цена.
/// </summary>
public partial class SyncViewModel : ViewModelBase
{
    private readonly ScottClient _client;

    [ObservableProperty] private string _host = SettingsStore.Current.Host;
    [ObservableProperty] private string _code = "";
    [ObservableProperty] private bool _busy;
    [ObservableProperty] private string _status = "";
    [ObservableProperty] private bool _statusIsError;

    public bool Paired => SettingsStore.Current.Paired;
    public bool NotPaired => !Paired;
    public string PairedHost => SettingsStore.Current.Host;

    public SyncViewModel(ScottClient client)
    {
        _client = client;
    }

    /// <summary>Кого извещать, когда привязка появилась или пропала.</summary>
    public System.Action? PairingChanged { get; set; }

    [RelayCommand]
    private async Task Pair()
    {
        var адрес = (Host ?? "").Trim();
        var код = (Code ?? "").Trim();

        if (адрес.Length == 0)
        {
            Показать("Впишите адрес компьютера — он виден в Scott, раздел «Удалённо»", ошибка: true);
            return;
        }

        if (код.Length == 0)
        {
            Показать("Впишите код с экрана компьютера", ошибка: true);
            return;
        }

        Busy = true;
        try
        {
            // Адрес проверяется до кода нарочно. Перепутанный адрес и неверный
            // код для человека выглядят одинаково — «не вышло», — а чинятся
            // по-разному: один переспрашивают у компьютера, другой набирают
            // заново, пока не истёк.
            if (!await _client.ReachableAsync(адрес))
            {
                Показать($"По адресу {адрес} никто не отвечает. Проверьте, что компьютер "
                         + "включён, находится в той же сети и доступ по сети разрешён "
                         + "в разделе «Удалённо».", ошибка: true);
                return;
            }

            var (успех, ключ, ошибка) = await _client.PairAsync(адрес, код, "Телефон");

            if (!успех)
            {
                Показать(ошибка, ошибка: true);
                return;
            }

            var настройки = SettingsStore.Current;
            настройки.Host = адрес;
            настройки.Token = ключ;
            настройки.DeviceName = "Телефон";
            SettingsStore.Save();

            Code = "";
            Показать("Готово. Теперь можно командовать Scott отсюда.", ошибка: false);

            Обновить();
        }
        finally
        {
            Busy = false;
        }
    }

    /// <summary>
    /// Отвязаться со стороны телефона.
    ///
    /// Честно говорим, чего это не делает: компьютер по-прежнему помнит это
    /// устройство. Потерянный телефон отвязывают ТАМ — здесь его в руках уже
    /// нет.
    /// </summary>
    [RelayCommand]
    private void Forget()
    {
        SettingsStore.Unpair();
        Host = "";
        Показать("Привязка забыта на этом телефоне. На компьютере устройство "
                 + "остаётся в списке — уберите его там, в разделе «Удалённо».", ошибка: false);

        Обновить();
    }

    [RelayCommand]
    private async Task Check()
    {
        if (!Paired)
        {
            return;
        }

        Busy = true;
        try
        {
            var отвечает = await _client.ReachableAsync(SettingsStore.Current.Host);

            Показать(отвечает
                ? "Компьютер на связи."
                : "Компьютер не отвечает. Дома он на связи, а из другой сети — нет: "
                  + "туда команды идут через Telegram.", ошибка: !отвечает);
        }
        finally
        {
            Busy = false;
        }
    }

    private void Показать(string текст, bool ошибка)
    {
        Status = текст;
        StatusIsError = ошибка;
    }

    private void Обновить()
    {
        OnPropertyChanged(nameof(Paired));
        OnPropertyChanged(nameof(NotPaired));
        OnPropertyChanged(nameof(PairedHost));
        PairingChanged?.Invoke();
    }
}
