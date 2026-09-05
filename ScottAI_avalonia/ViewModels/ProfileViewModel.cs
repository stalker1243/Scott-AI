using System;
using System.IO;
using Avalonia;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
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

    public ProfileViewModel()
    {
        _avatarBytes = SettingsStore.LoadAvatar();
        if (_avatarBytes != null)
        {
            LoadBitmap(_avatarBytes);
        }
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
