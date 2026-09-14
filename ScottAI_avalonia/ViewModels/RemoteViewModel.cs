using System.Collections.ObjectModel;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>
/// Кто может командовать Scott издалека.
///
/// Раздел существует ради двух вещей, и обе про доверие. Первая: человек должен
/// ВИДЕТЬ, какие устройства имеют доступ к его компьютеру, и отвязать любое
/// одним нажатием. Вторая: он должен видеть, что именно они делали, — иначе о
/// чужой команде не узнать никогда.
///
/// Привязка идёт отсюда, а не с телефона: код показывается на экране
/// компьютера, и это единственное доказательство, что привязывающий сидит за
/// этим самым компьютером.
/// </summary>
public partial class RemoteViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    public ObservableCollection<RemoteDevice> Devices { get; } = new();
    public ObservableCollection<RemoteLogEntry> Log { get; } = new();

    [ObservableProperty] private RemoteBridge _bridge = new();
    [ObservableProperty] private string _tokenInput = "";
    [ObservableProperty] private bool _busy;
    [ObservableProperty] private string? _error;

    /// <summary>Код привязки. Пока он показан, телефон может привязаться.</summary>
    [ObservableProperty] private string _pairingCode = "";
    [ObservableProperty] private int _pairingSeconds;

    public bool HasCode => PairingCode.Length > 0;
    public bool NoDevices => Devices.Count == 0;
    public bool BridgeWorks => Bridge.Running;

    partial void OnPairingCodeChanged(string value) => OnPropertyChanged(nameof(HasCode));
    partial void OnBridgeChanged(RemoteBridge value) => OnPropertyChanged(nameof(BridgeWorks));

    public RemoteViewModel(BackendClient client)
    {
        _client = client;
    }

    [RelayCommand]
    public async Task Refresh()
    {
        var состояние = await _client.RemoteStatusAsync();

        if (состояние is null)
        {
            Error = "Backend не отвечает";
            return;
        }

        Error = null;
        Bridge = состояние.Bridge;

        Devices.Clear();
        foreach (var устройство in состояние.Devices)
        {
            Devices.Add(устройство);
        }

        Log.Clear();
        var записи = await _client.RemoteLogAsync();

        // Свежее сверху: журнал смотрят, чтобы узнать, что было только что.
        for (var i = записи.Count - 1; i >= 0; i--)
        {
            Log.Add(записи[i]);
        }

        OnPropertyChanged(nameof(NoDevices));
    }

    [RelayCommand]
    private async Task ConnectTelegram()
    {
        var токен = (TokenInput ?? "").Trim();
        if (токен.Length == 0)
        {
            ToastService.Error("Вставьте токен бота — его выдаёт @BotFather");
            return;
        }

        Busy = true;
        try
        {
            var (успех, сообщение) = await _client.SetupTelegramAsync(токен);

            if (!успех)
            {
                ToastService.Error(сообщение.Length > 0 ? сообщение : "Telegram не принял токен");
                return;
            }

            // Токен убираем с экрана сразу: он больше не нужен, а лежать на
            // виду ему незачем — это ключ от Scott.
            TokenInput = "";
            ToastService.Success($"Бот подключён: @{сообщение}");

            await Refresh();
        }
        finally
        {
            Busy = false;
        }
    }

    /// <summary>
    /// Показать код привязки.
    ///
    /// Живёт минуту: столько нужно, чтобы прочитать его с экрана и набрать на
    /// телефоне. Дольше — и он успеет попасть на снимок экрана и в чужие глаза.
    /// </summary>
    [RelayCommand]
    private async Task StartPairing()
    {
        var (код, секунды) = await _client.StartPairingAsync();

        if (код.Length == 0)
        {
            ToastService.Error("Не удалось получить код");
            return;
        }

        PairingCode = код;
        PairingSeconds = секунды;

        // Обратный отсчёт: человек должен видеть, сколько у него осталось, а не
        // обнаружить истёкший код по отказу на телефоне.
        while (PairingSeconds > 0 && PairingCode == код)
        {
            await Task.Delay(1000);
            PairingSeconds--;
        }

        if (PairingCode == код)
        {
            PairingCode = "";
        }

        await Refresh();
    }

    [RelayCommand]
    private async Task Forget(RemoteDevice? устройство)
    {
        if (устройство is null)
        {
            return;
        }

        var согласен = await DialogService.ConfirmAsync(
            $"Отвязать «{устройство.Name}»?",
            "Это устройство больше не сможет командовать Scott. Привязать его снова можно в любой момент — новым кодом.",
            "Отвязать");

        if (!согласен)
        {
            return;
        }

        if (!await _client.ForgetDeviceAsync(устройство.Id))
        {
            ToastService.Error("Не удалось отвязать");
            return;
        }

        ToastService.Success("Устройство отвязано");
        await Refresh();
    }
}
