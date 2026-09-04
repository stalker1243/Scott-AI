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

    [ObservableProperty]
    private bool _isDark = true;

    [ObservableProperty]
    private string _currentStyle = "classic"; // "classic" | "glass" | "terminal"

    public ObservableCollection<AccentSwatch> AccentSwatches { get; } = new(
        new[] { "#3B82F6", "#22C55E", "#A855F7", "#F59E0B", "#EF4444", "#00FFF2" }.Select(h => new AccentSwatch(h)));

    [ObservableProperty]
    private string _currentAccentHex = "#3B82F6";

    [ObservableProperty]
    private double _glassOpacity = ThemeService.GlassOpacityPercent;

    partial void OnGlassOpacityChanged(double value) => ThemeService.SetGlassOpacity(value);

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
    }

    [RelayCommand]
    private void SetStyleClassic()
    {
        CurrentStyle = "classic";
        ThemeService.ApplyStyle(AppStyle.Classic, IsDark);
        SyncAccentSelection();
    }

    [RelayCommand]
    private void SetStyleGlass()
    {
        CurrentStyle = "glass";
        ThemeService.ApplyStyle(AppStyle.Glass);
        SyncAccentSelection();
    }

    [RelayCommand]
    private void SetStyleTerminal()
    {
        CurrentStyle = "terminal";
        ThemeService.ApplyStyle(AppStyle.Terminal);
        SyncAccentSelection();
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
    }

    [RelayCommand]
    private void SetAccent(AccentSwatch swatch)
    {
        ThemeService.SetAccent(Color.Parse(swatch.Hex));
        CurrentAccentHex = swatch.Hex;
        SyncAccentSelection();
    }

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
