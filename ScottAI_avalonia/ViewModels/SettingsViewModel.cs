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

    /// <summary>
    /// Кого предупредить, что оформление сброшено.
    ///
    /// Сама страница оформления — отдельный раздел, и её переключатели после
    /// сброса показывали бы прежнее, пока человек не перезапустит лаунчер.
    /// </summary>
    private readonly System.Action? _onAppearanceReset;

    /// <summary>Открытый раздел настроек: "voice" | "ai" | "other".</summary>
    [ObservableProperty]
    private string _settingsTab = "voice";

    [RelayCommand]
    private void SetSettingsTab(string tab) => SettingsTab = tab;

    [ObservableProperty] private bool _aiLoading;

    // ---- Голос Scott ----
    // Показываем только мужские голоса (фильтрация на стороне backend), из обоих
    // движков сразу: локального Silero и облачного Edge TTS.
    public ObservableCollection<VoiceOption> Voices { get; } = new();

    /// <summary>
    /// Характеры звучания — обработка, которой пропускается синтезированная речь.
    ///
    /// Голосов у локальной модели пять, и все обычные человеческие: сделать
    /// звучание узнаваемым сменой голоса нельзя, а обработкой — можно.
    /// </summary>
    public ObservableCollection<VoiceCharacter> Characters { get; } = new();

    [ObservableProperty] private VoiceCharacter? _selectedCharacter;

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

    public SettingsViewModel(BackendClient client, System.Action? onAppearanceReset = null)
    {
        _onAppearanceReset = onAppearanceReset;
        _client = client;
        _ = LoadVersions();
        _ = LoadVoices();
        _ = LoadCharacters();
        _ = LoadDeviceSettings();
        _ = LoadAudioSettings();

        // То же, что и на других страницах: при запуске backend ещё не готов,
        // и списки провайдеров, голосов и устройств приходили пустыми.
        BackendReady.WhenReady(() =>
        {
            _ = LoadVersions();
            _ = LoadVoices();
            _ = LoadDeviceSettings();
            _ = LoadAudioSettings();
        });
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

    /// <summary>Сбросить профиль и оформление к первоначальному виду.</summary>
    [RelayCommand]
    private void ResetSettings()
    {
        SettingsStore.Reset();

        // Оформление применяем сразу: иначе окно осталось бы в прежнем виде до
        // перезапуска, и человек решил бы, что сброс не сработал.
        ThemeService.ApplySaved(SettingsStore.Current);

        // И сообщаем разделу «Внешний вид», что его переключатели устарели:
        // оформление живёт теперь там, а сброс делается отсюда.
        _onAppearanceReset?.Invoke();

        ToastService.Success("Настройки сброшены — имя, «о себе», аватар и оформление очищены");
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

    private async Task LoadCharacters()
    {
        var ответ = await _client.VoiceCharactersAsync();

        if (ответ is null)
        {
            return;
        }

        Characters.Clear();
        foreach (var характер in ответ.Characters)
        {
            Characters.Add(характер);
        }

        // Выбранным показываем тот, которым Scott говорит сейчас: список,
        // показывающий не то, что происходит, хуже отсутствующего.
        SelectedCharacter = Characters.FirstOrDefault(х => х.Id == ответ.Current)
                            ?? Characters.FirstOrDefault();
        Отметить();
    }

    private void Отметить()
    {
        foreach (var характер in Characters)
        {
            характер.Selected = характер.Id == SelectedCharacter?.Id;
        }
    }

    /// <summary>
    /// Выбрать характер звучания.
    ///
    /// Применяется сразу, без кнопки «применить»: звучание проверяют на слух,
    /// а не по памяти — кнопкой «Прослушать» тут же, рядом.
    /// </summary>
    [RelayCommand]
    private async Task PickCharacter(VoiceCharacter? характер)
    {
        if (характер is null || характер.Id == SelectedCharacter?.Id)
        {
            return;
        }

        SelectedCharacter = характер;
        Отметить();

        if (await _client.SelectVoiceCharacterAsync(характер.Id))
        {
            ToastService.Success($"Звучание: {характер.Name}");
        }
        else
        {
            ToastService.Error("Не удалось применить характер звучания");
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
            // force: прослушивание звучит и в тихом режиме — человек нажал
            // кнопку и ждёт голос именно сейчас.
            await _client.SpeakAsync("Скотт на связи. Все системы работают в штатном режиме.", force: true);
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

    // ==================== Звук: устройства, громкость, тихий режим ====================

    /// <summary>Микрофоны в системе. Первым элементом всегда «как в системе».</summary>
    public ObservableCollection<AudioDevice> InputDevices { get; } = new();

    /// <summary>Динамики и наушники в системе.</summary>
    public ObservableCollection<AudioDevice> OutputDevices { get; } = new();

    [ObservableProperty]
    private AudioDevice? _selectedInputDevice;

    [ObservableProperty]
    private AudioDevice? _selectedOutputDevice;

    [ObservableProperty]
    private double _speechVolume = 100;

    [ObservableProperty]
    private bool _quietMode;

    /// <summary>Есть ли на машине звуковая подсистема вообще.</summary>
    [ObservableProperty]
    private bool _audioAvailable = true;

    [ObservableProperty]
    private string? _audioStatus;

    /// <summary>
    /// Пока идёт загрузка, изменения полей не отправляются обратно.
    ///
    /// Без этого заполнение списков само выглядело бы как выбор пользователя, и
    /// Scott сохранял бы то, чего никто не выбирал.
    /// </summary>
    private bool _audioLoading;

    /// <summary>
    /// Отложенная запись громкости.
    ///
    /// Ползунок шлёт событие на каждый пиксель движения, а каждое сохранение —
    /// это запись файла на диск. Ждём, пока человек остановится.
    /// </summary>
    private System.Threading.CancellationTokenSource? _volumeDelay;

    private async Task LoadAudioSettings()
    {
        _audioLoading = true;
        try
        {
            var state = await _client.GetAudioAsync();
            if (state is null)
            {
                AudioStatus = "backend не отвечает — настройки звука недоступны";
                return;
            }

            AudioAvailable = state.Available;
            AudioStatus = state.Available
                ? null
                : "Звуковая подсистема недоступна: Scott не сможет ни говорить, ни слышать.";

            FillDevices(InputDevices, state.Devices.Input);
            FillDevices(OutputDevices, state.Devices.Output);

            SelectedInputDevice = FindDevice(InputDevices, state.Settings.InputDevice);
            SelectedOutputDevice = FindDevice(OutputDevices, state.Settings.OutputDevice);
            SpeechVolume = state.Settings.Volume;
            QuietMode = state.Settings.Quiet;
        }
        catch (System.Exception ex)
        {
            AudioStatus = $"Не удалось прочитать настройки звука: {ex.Message}";
        }
        finally
        {
            _audioLoading = false;
        }
    }

    /// <summary>Заполнить список, поставив первым выбор «как в системе».</summary>
    private static void FillDevices(ObservableCollection<AudioDevice> target, System.Collections.Generic.List<AudioDevice> found)
    {
        target.Clear();
        target.Add(new AudioDevice { Name = "" });
        foreach (var device in found) target.Add(device);
    }

    /// <summary>
    /// Найти сохранённое устройство по имени.
    ///
    /// Если его больше нет — наушники отключили, — возвращаемся к системному, а
    /// не оставляем список без выбора: пустая строка выглядела бы поломкой.
    /// </summary>
    private static AudioDevice? FindDevice(ObservableCollection<AudioDevice> devices, string name)
    {
        return devices.FirstOrDefault(d => d.Name == name) ?? devices.FirstOrDefault();
    }

    partial void OnSelectedInputDeviceChanged(AudioDevice? value)
    {
        if (_audioLoading || value is null) return;
        _ = PushAudio(new { input_device = value.Name });
    }

    partial void OnSelectedOutputDeviceChanged(AudioDevice? value)
    {
        if (_audioLoading || value is null) return;
        _ = PushAudio(new { output_device = value.Name });
    }

    partial void OnSpeechVolumeChanged(double value)
    {
        if (_audioLoading) return;
        _ = PushVolumeSoon((int)System.Math.Round(value));
    }

    partial void OnQuietModeChanged(bool value)
    {
        if (_audioLoading) return;
        _ = _client.SetQuietAsync(value);
    }

    private async Task PushVolumeSoon(int volume)
    {
        _volumeDelay?.Cancel();
        var delay = new System.Threading.CancellationTokenSource();
        _volumeDelay = delay;

        try
        {
            await Task.Delay(400, delay.Token);
        }
        catch (System.OperationCanceledException)
        {
            // Ползунок поехал дальше — сохранит следующее событие.
            return;
        }

        await PushAudio(new { volume });
    }

    private async Task PushAudio(object changes)
    {
        try
        {
            var state = await _client.SetAudioAsync(changes);
            AudioStatus = state?.Success == true ? null : "Не удалось сохранить настройку звука";
        }
        catch (System.Exception ex)
        {
            AudioStatus = $"Не удалось сохранить: {ex.Message}";
        }
    }

    /// <summary>Кнопка «Прослушать» рядом с громкостью — чтобы подобрать её на слух.</summary>
    [RelayCommand]
    private async Task TestVolume()
    {
        // force: иначе в тихом режиме кнопка молчала бы, и человек решил бы,
        // что сломана именно она.
        await _client.SpeakAsync("Так меня будет слышно.", force: true);
    }
}
