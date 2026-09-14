using System;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using Avalonia;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public partial class ProfileViewModel : ViewModelBase
{
    /// <summary>Сторона квадратной области, в которой человек подбирает кадр.</summary>
    public const double FrameSize = 220;

    /// <summary>Дальше 4× приближать бессмысленно — видны только пиксели.</summary>
    private const double MaxZoom = 4.0;

    [ObservableProperty] private string _name = SettingsStore.Current.UserName;
    [ObservableProperty] private string _bio = SettingsStore.Current.Bio;
    [ObservableProperty] private bool _savedRecently;

    // ---- Персонализация ----
    //
    // Раньше имя и рассказ о себе оставались в настройках лаунчера и до Scott
    // не доходили вовсе: человек писал «я программист», а ответы получал ровно
    // те же, что и все. Теперь всё это уходит на backend и подмешивается к
    // указанию модели в каждом запросе.

    /// <summary>Характеры приходят с backend: добавленный там появится сам.</summary>
    public ObservableCollection<PersonalityStyle> Styles { get; } = new();

    /// <summary>Слова, которыми человек описал свои интересы.</summary>
    public ObservableCollection<string> Interests { get; } = new();

    [ObservableProperty] private PersonalityStyle? _selectedStyle;

    /// <summary>Что набрано в поле добавления интереса.</summary>
    [ObservableProperty] private string _newInterest = "";

    /// <summary>
    /// Предел длины рассказа о себе.
    ///
    /// Он уходит в каждый запрос к модели, и backend всё равно обрежет его до
    /// той же величины. Показываем счётчик заранее, чтобы обрезка не стала
    /// неожиданностью уже после сохранения.
    /// </summary>
    public const int AboutLimit = 300;

    public string AboutCounter => $"{Bio?.Length ?? 0} / {AboutLimit}";

    partial void OnBioChanged(string value) => OnPropertyChanged(nameof(AboutCounter));
    [ObservableProperty] private Bitmap? _avatarImage;

    /// <summary>
    /// Байты выбранной картинки. Держим их отдельно от Bitmap, потому что
    /// записать на диск нужно исходный файл, а Bitmap — уже декодированное
    /// изображение, из которого обратно PNG без потерь не собрать.
    /// null означает, что аватара нет — и при сохранении файл будет удалён.
    /// </summary>
    private byte[]? _avatarBytes;

    // ---- Кадрирование ----
    // Фото почти никогда не годится «как есть»: лицо смещено от центра, и
    // круглая рамка обрезает его как попало. Человек двигает снимок мышью и
    // подбирает увеличение, а сохраняется выбранная им часть.
    [ObservableProperty] private double _avatarOffsetX = SettingsStore.Current.AvatarOffsetX;
    [ObservableProperty] private double _avatarOffsetY = SettingsStore.Current.AvatarOffsetY;
    [ObservableProperty] private double _avatarZoom = SettingsStore.Current.AvatarZoom;

    /// <summary>
    /// Связь с backend — ради персонализации.
    ///
    /// Аватар и кадрирование живут в лаунчере и обойдутся без него, а характер
    /// и рассказ о себе уходят в разговор, и хранит их backend.
    /// </summary>
    private readonly BackendClient? _client;

    public ProfileViewModel(BackendClient? client = null)
    {
        _client = client;
        _avatarBytes = SettingsStore.LoadAvatar();
        if (_avatarBytes != null)
        {
            LoadBitmap(_avatarBytes);
        }

        _ = LoadPersonalityAsync();

        // Первый запрос уходит, пока backend ещё поднимается. Повторяем, когда
        // отвечать стало кому: иначе список характеров остался бы пустым до
        // перезапуска лаунчера.
        BackendReady.WhenReady(() => _ = LoadPersonalityAsync());
    }

    public bool HasAvatar => AvatarImage is not null;

    partial void OnAvatarImageChanged(Bitmap? value) => OnPropertyChanged(nameof(HasAvatar));

    partial void OnAvatarZoomChanged(double value) => ClampOffsets();

    /// <summary>
    /// Сдвинуть кадр мышью.
    ///
    /// Вызывается из code-behind: перетаскивание требует событий указателя,
    /// которые живут во View, а результат — обычные два числа.
    /// </summary>
    public void DragAvatar(double deltaX, double deltaY)
    {
        AvatarOffsetX += deltaX;
        AvatarOffsetY += deltaY;
        ClampOffsets();
    }

    /// <summary>Приблизить или отдалить колесом мыши.</summary>
    public void ZoomAvatar(double delta)
    {
        AvatarZoom = Math.Clamp(AvatarZoom + delta, 1.0, MaxZoom);
    }

    /// <summary>
    /// Не дать увести фото за пределы рамки.
    ///
    /// При увеличении 1 картинка ровно вписана, и двигать её некуда: любое
    /// смещение открыло бы пустой угол. Чем сильнее приближение, тем больше
    /// запас с каждой стороны — он и ограничивает сдвиг.
    /// </summary>
    private void ClampOffsets()
    {
        var slack = FrameSize * (AvatarZoom - 1) / 2;
        AvatarOffsetX = Math.Clamp(AvatarOffsetX, -slack, slack);
        AvatarOffsetY = Math.Clamp(AvatarOffsetY, -slack, slack);
    }

    [RelayCommand]
    private void ResetCrop()
    {
        AvatarZoom = 1.0;
        AvatarOffsetX = 0;
        AvatarOffsetY = 0;
    }

    /// <summary>
    /// Сохранить профиль. Кнопка фиксирует состояние страницы целиком — и имя
    /// с описанием, и аватар вместе с выбранным кадром: иначе выбор картинки
    /// записывался бы сразу, а имя по кнопке, и было бы неясно, что уже
    /// сохранено, а что нет.
    /// </summary>
    /// <summary>
    /// Забрать персонализацию с backend.
    ///
    /// Именно оттуда, а не из настроек лаунчера: она уходит в разговор, и
    /// показывать надо то, что в разговоре и участвует. Разойдись эти два
    /// хранилища — человек видел бы на экране одно, а Scott вёл себя по
    /// другому.
    /// </summary>
    public async System.Threading.Tasks.Task LoadPersonalityAsync()
    {
        var данные = _client is null ? null : await _client.PersonalityAsync();
        if (данные is null)
        {
            return;
        }

        Styles.Clear();
        foreach (var стиль in данные.Styles)
        {
            Styles.Add(стиль);
        }

        SelectedStyle = Styles.FirstOrDefault(с => с.Id == данные.Style) ?? Styles.FirstOrDefault();

        Interests.Clear();
        foreach (var интерес in данные.Interests)
        {
            Interests.Add(интерес);
        }

        // Имя и рассказ берём с backend, только если там что-то есть: иначе
        // первое открытие страницы стёрло бы то, что человек уже вписал в
        // лаунчере до всей этой затеи.
        if (!string.IsNullOrWhiteSpace(данные.Name)) Name = данные.Name;
        if (!string.IsNullOrWhiteSpace(данные.About)) Bio = данные.About;
    }

    [RelayCommand]
    private void AddInterest()
    {
        var слово = (NewInterest ?? "").Trim();
        if (слово.Length == 0 || Interests.Contains(слово))
        {
            NewInterest = "";
            return;
        }

        Interests.Add(слово);
        NewInterest = "";
    }

    [RelayCommand]
    private void RemoveInterest(string? слово)
    {
        if (слово is not null)
        {
            Interests.Remove(слово);
        }
    }

    [RelayCommand]
    private async System.Threading.Tasks.Task Save()
    {
        var settings = SettingsStore.Current;
        settings.UserName = Name;
        settings.Bio = Bio;
        settings.AvatarOffsetX = AvatarOffsetX;
        settings.AvatarOffsetY = AvatarOffsetY;
        settings.AvatarZoom = AvatarZoom;
        SettingsStore.SaveCurrent();
        SettingsStore.SaveAvatar(_avatarBytes);

        // На backend — то, что участвует в разговоре. Возвращённое оттуда
        // показываем как есть: длинный рассказ о себе он обрежет, и человек
        // должен увидеть именно сохранённое.
        if (_client is not null)
        {
            var сохранено = await _client.SavePersonalityAsync(new
            {
                style = SelectedStyle?.Id ?? "friendly",
                about = Bio ?? "",
                interests = Interests.ToList(),
                name = Name ?? "",
            });

            if (сохранено is not null)
            {
                Bio = сохранено.About;

                Interests.Clear();
                foreach (var интерес in сохранено.Interests)
                {
                    Interests.Add(интерес);
                }
            }
        }

        SavedRecently = true;
        await System.Threading.Tasks.Task.Delay(2000);
        SavedRecently = false;
    }

    /// <summary>Вызывается из code-behind View после выбора файла через StorageProvider (нужен доступ к TopLevel, поэтому сам пикер живёт в View).</summary>
    public void SetAvatarFromBytes(byte[] bytes)
    {
        _avatarBytes = bytes;
        LoadBitmap(bytes);
        // Новый снимок — новый кадр: прежние сдвиг и увеличение относятся к
        // другой картинке и почти наверняка обрежут эту неудачно.
        ResetCrop();
    }

    [RelayCommand]
    private void RemoveAvatar()
    {
        _avatarBytes = null;
        AvatarImage = null;
        ResetCrop();
    }

    private void LoadBitmap(byte[] bytes)
    {
        try
        {
            using var ms = new MemoryStream(bytes);
            AvatarImage = new Bitmap(ms);
        }
        catch (Exception)
        {
            // Файл на диске оказался не картинкой (или повреждён) — показываем
            // заглушку вместо аватара, а не роняем страницу профиля.
            _avatarBytes = null;
            AvatarImage = null;
        }
    }
}
