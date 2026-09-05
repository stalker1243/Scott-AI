using System.Collections.ObjectModel;
using System.Linq;
using System.Threading.Tasks;
using Avalonia.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public partial class SettingsViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    // Стартовые значения — те, что остались с прошлого запуска. Само оформление
    // к этому моменту уже применено в App (до создания окна), здесь лишь
    // приводится в соответствие состояние переключателей на странице.
    [ObservableProperty]
    private bool _isDark = SettingsStore.Current.IsDark;

    [ObservableProperty]
    private string _currentStyle = SettingsStore.Current.Style; // "classic" | "glass" | "terminal"

    public ObservableCollection<AccentSwatch> AccentSwatches { get; } = new(
        new[] { "#3B82F6", "#22C55E", "#A855F7", "#F59E0B", "#EF4444", "#00FFF2" }.Select(h => new AccentSwatch(h)));

    [ObservableProperty]
    private string _currentAccentHex = "#3B82F6";

    [ObservableProperty]
    private double _glassOpacity = ThemeService.GlassOpacityPercent;

    partial void OnGlassOpacityChanged(double value)
    {
        ThemeService.SetGlassOpacity(value);
        PersistTheme();
    }

    /// <summary>
    /// Запомнить оформление на следующий запуск. Снимок берётся с ThemeService,
    /// а не с полей страницы: акцент он сбрасывает сам при смене стиля, и только
    /// он знает, какой цвет в итоге применён.
    /// </summary>
    private void PersistTheme()
    {
        var settings = SettingsStore.Current;
        settings.Style = CurrentStyle;
        settings.IsDark = ThemeService.IsDark;
        settings.AccentHex = ThemeService.CurrentAccentHex;
        settings.GlassOpacity = ThemeService.GlassOpacityPercent;
        SettingsStore.SaveCurrent();
    }

    // ---- Модель ИИ ----
    public ObservableCollection<AiProvider> Providers { get; } = new();

    [ObservableProperty] private AiProvider? _selectedProvider;
    [ObservableProperty] private string? _selectedModel;
    [ObservableProperty] private string _apiKeyInput = "";
    [ObservableProperty] private string? _activeProvider;
    [ObservableProperty] private string _activeModel = "";
    [ObservableProperty] private bool _aiApplying;
    [ObservableProperty] private string? _aiError;
    [ObservableProperty] private string? _aiStatus;
    [ObservableProperty] private bool _aiLoading;

    // ---- Голос Scott ----
    // Показываем только мужские голоса (фильтрация на стороне backend), из обоих
    // движков сразу: локального Silero и облачного Edge TTS.
    public ObservableCollection<VoiceOption> Voices { get; } = new();

    [ObservableProperty] private VoiceOption? _selectedVoice;
    [ObservableProperty] private bool _voicesLoading;
    [ObservableProperty] private string? _voiceStatus;
    [ObservableProperty] private bool _voiceBusy;

    // ---- Фоновая работа ----
    // Для голосового ассистента работа в фоне — состояние по умолчанию: смысл
    // в том, чтобы услышать обращение тогда, когда окно давно закрыто.
    [ObservableProperty] private bool _runInBackground = SettingsStore.Current.RunInBackground;

    partial void OnRunInBackgroundChanged(bool value)
    {
        SettingsStore.Current.RunInBackground = value;
        SettingsStore.SaveCurrent();
    }

    // ---- Устройство для речи ----
    // Автовыбор берёт видеокарту, когда она есть: разница принципиальная —
    // распознавание фразы занимает около секунды против четырёх с половиной на
    // процессоре. Ручной выбор нужен как аварийный выход: видеокарту может
    // занять игра, драйвер — сбоить.
    [ObservableProperty] private string _deviceChoice = "auto";
    [ObservableProperty] private string _deviceInUse = "";
    [ObservableProperty] private bool _cudaAvailable;
    [ObservableProperty] private bool _deviceLockedByEnv;
    [ObservableProperty] private string _deviceEnvVar = "";
    [ObservableProperty] private bool _deviceBusy;
    [ObservableProperty] private string? _deviceStatus;

    public bool DeviceIsAuto => DeviceChoice == "auto";
    public bool DeviceIsGpu => DeviceChoice == "cuda";
    public bool DeviceIsCpu => DeviceChoice == "cpu";

    partial void OnDeviceChoiceChanged(string value)
    {
        OnPropertyChanged(nameof(DeviceIsAuto));
        OnPropertyChanged(nameof(DeviceIsGpu));
        OnPropertyChanged(nameof(DeviceIsCpu));
    }

    // ---- Версии ----
    public ObservableCollection<VersionItem> VersionedItems { get; } = new();
    [ObservableProperty] private bool _versionsLoading;
    [ObservableProperty] private string? _versionsError;

    public SettingsViewModel(BackendClient client)
    {
        _client = client;
        SyncAccentSelection();
        _ = LoadAiProviders();
        _ = LoadVersions();
        _ = LoadVoices();
        _ = LoadDeviceSettings();
    }

    [RelayCommand]
    private void SetStyleClassic()
    {
        CurrentStyle = "classic";
        ThemeService.ApplyStyle(AppStyle.Classic, IsDark);
        SyncAccentSelection();
        PersistTheme();
    }

    [RelayCommand]
    private void SetStyleGlass()
    {
        CurrentStyle = "glass";
        ThemeService.ApplyStyle(AppStyle.Glass);
        SyncAccentSelection();
        PersistTheme();
    }

    [RelayCommand]
    private void SetStyleTerminal()
    {
        CurrentStyle = "terminal";
        ThemeService.ApplyStyle(AppStyle.Terminal);
        SyncAccentSelection();
        PersistTheme();
    }

    [RelayCommand]
    private void SetDark()
    {
        IsDark = true;
        if (CurrentStyle == "classic")
        {
            ThemeService.ApplyStyle(AppStyle.Classic, true);
            SyncAccentSelection();
        }
        PersistTheme();
    }

    [RelayCommand]
    private void SetLight()
    {
        IsDark = false;
        if (CurrentStyle == "classic")
        {
            ThemeService.ApplyStyle(AppStyle.Classic, false);
            SyncAccentSelection();
        }
        PersistTheme();
    }

    [RelayCommand]
    private void SetAccent(AccentSwatch swatch)
    {
        ThemeService.SetAccent(Color.Parse(swatch.Hex));
        CurrentAccentHex = swatch.Hex;
        SyncAccentSelection();
        PersistTheme();
    }

    [RelayCommand]
    private async Task LoadDeviceSettings()
    {
        var state = await _client.DeviceSettingsAsync();
        ApplyDeviceState(state);
    }

    private void ApplyDeviceState(DeviceSettingsResponse? state)
    {
        if (state is null)
        {
            DeviceInUse = "backend не отвечает";
            return;
        }

        CudaAvailable = state.CudaAvailable;

        // Показываем состояние распознавания: оно дороже синтеза и заметнее для
        // пользователя, а переключаются оба движка вместе.
        if (state.Engines.TryGetValue("whisper", out var whisper))
        {
            DeviceChoice = whisper.Choice;
            DeviceInUse = whisper.Device == "cuda" ? "видеокарта" : "процессор";
            DeviceLockedByEnv = whisper.LockedByEnv;
            DeviceEnvVar = whisper.EnvVar;
        }
    }

    /// <summary>
    /// Переключить оба движка сразу.
    ///
    /// Разделять их незачем: пользователь мыслит категорией «на чём работает
    /// Scott», а не «на чём Whisper и отдельно Silero».
    /// </summary>
    private async Task SetDevice(string choice)
    {
        DeviceBusy = true;
        DeviceStatus = null;
        try
        {
            var (success, message, state) = await _client.SetDeviceAsync("whisper", choice);
            if (!success)
            {
                DeviceStatus = message;
                ToastService.Error(message);
                return;
            }

            // Silero переключаем следом; если он откажется, распознавание уже
            // переехало, и состояние покажет ровно это.
            await _client.SetDeviceAsync("silero", choice);

            ApplyDeviceState(state);
            await LoadDeviceSettings();
            DeviceStatus = "Модели перезагрузятся при следующей фразе";
            ToastService.Success($"Устройство: {DeviceInUse}");
        }
        finally
        {
            DeviceBusy = false;
        }
    }

    [RelayCommand]
    private Task SetDeviceAuto() => SetDevice("auto");

    [RelayCommand]
    private Task SetDeviceGpu() => SetDevice("cuda");

    [RelayCommand]
    private Task SetDeviceCpu() => SetDevice("cpu");

    private void SyncAccentSelection()
    {
        CurrentAccentHex = ThemeService.CurrentAccentHex;
        foreach (var swatch in AccentSwatches)
            swatch.IsSelected = string.Equals(swatch.Hex, CurrentAccentHex, System.StringComparison.OrdinalIgnoreCase);
    }

    [RelayCommand]
    private async Task LoadAiProviders()
    {
        AiLoading = true;
        AiError = null;
        try
        {
            var (providers, activeProvider, activeModel) = await _client.ListAiProvidersAsync();
            Providers.Clear();
            foreach (var p in providers) Providers.Add(p);
            ActiveProvider = activeProvider;
            ActiveModel = activeModel;
            SelectedProvider = Providers.Count > 0
                ? (Providers.FirstOrDefault(p => p.Id == activeProvider) ?? Providers[0])
                : null;
            SelectedModel = activeModel;
        }
        catch (System.Exception ex)
        {
            AiError = ex.Message;
        }
        finally
        {
            AiLoading = false;
        }
    }

    [RelayCommand]
    private void SetSelectedProvider(AiProvider provider) => SelectedProvider = provider;

    partial void OnSelectedProviderChanged(AiProvider? value)
    {
        ApiKeyInput = "";
        SelectedModel = value?.Id == ActiveProvider ? ActiveModel : value?.Models.Count > 0 ? value.Models[0].Id : null;
    }

    [RelayCommand]
    private async Task ApplyAi()
    {
        if (SelectedProvider is null || string.IsNullOrWhiteSpace(SelectedModel)) return;
        AiApplying = true;
        AiError = null;
        AiStatus = null;
        try
        {
            var (success, message) = await _client.ConfigureAiAsync(SelectedProvider.Id, SelectedModel, string.IsNullOrWhiteSpace(ApiKeyInput) ? null : ApiKeyInput.Trim());
            if (!success)
            {
                AiError = message;
                ToastService.Error(message);
                return;
            }
            ApiKeyInput = "";
            AiStatus = message;
            ToastService.Success($"Модель ИИ переключена на {SelectedProvider.Id}");
            await LoadAiProviders();
        }
        finally
        {
            AiApplying = false;
        }
    }

    [RelayCommand]
    private async Task LoadVoices()
    {
        VoicesLoading = true;
        VoiceStatus = null;
        try
        {
            var (voices, current) = await _client.ListVoicesAsync("male");
            Voices.Clear();
            foreach (var v in voices) Voices.Add(v);

            // Выставляем выбранным тот голос, которым Scott говорит прямо сейчас,
            // чтобы список не показывал не то, что происходит на самом деле.
            _suppressVoiceApply = true;
            SelectedVoice = Voices.FirstOrDefault(v => v.Id == current) ?? Voices.FirstOrDefault();
            _suppressVoiceApply = false;
        }
        catch (System.Exception ex)
        {
            VoiceStatus = $"Не удалось получить список голосов: {ex.Message}";
        }
        finally
        {
            VoicesLoading = false;
        }
    }

    // Выбор голоса применяется сразу при переключении в списке. Флаг нужен, чтобы
    // программная установка SelectedVoice (при загрузке) не считалась выбором
    // пользователя и не дёргала backend впустую.
    private bool _suppressVoiceApply;

    partial void OnSelectedVoiceChanged(VoiceOption? value)
    {
        if (_suppressVoiceApply || value is null) return;
        _ = ApplyVoice(value);
    }

    private async Task ApplyVoice(VoiceOption voice)
    {
        VoiceBusy = true;
        VoiceStatus = null;
        try
        {
            var (success, message) = await _client.SelectVoiceAsync(voice.Id);
            if (success)
            {
                ToastService.Success($"Голос: {voice.Label}");
            }
            else
            {
                VoiceStatus = message;
                ToastService.Error(message);
            }
        }
        catch (System.Exception ex)
        {
            VoiceStatus = ex.Message;
            ToastService.Error($"Не удалось сменить голос: {ex.Message}");
        }
        finally
        {
            VoiceBusy = false;
        }
    }

    /// <summary>Дать Scott произнести пробную фразу текущим голосом — выбирать тембр
    /// имеет смысл только на слух, по названию этого не понять.</summary>
    [RelayCommand]
    private async Task PreviewVoice()
    {
        if (SelectedVoice is null) return;

        VoiceBusy = true;
        try
        {
            // Сначала переключаем голос, иначе backend озвучит предыдущим.
            await _client.SelectVoiceAsync(SelectedVoice.Id);
            await _client.SpeakAsync("Скотт на связи. Все системы работают в штатном режиме.");
        }
        catch (System.Exception ex)
        {
            ToastService.Error($"Не удалось воспроизвести: {ex.Message}");
        }
        finally
        {
            VoiceBusy = false;
        }
    }

    [RelayCommand]
    private async Task LoadVersions()
    {
        VersionsLoading = true;
        VersionsError = null;
        try
        {
            var items = await _client.ListVersionedItemsAsync();
            VersionedItems.Clear();
            foreach (var i in items) VersionedItems.Add(i);
        }
        catch (System.Exception ex)
        {
            VersionsError = ex.Message;
        }
        finally
        {
            VersionsLoading = false;
        }
    }
}
