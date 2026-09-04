using System.IO;
using Avalonia.Media.Imaging;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public partial class ProfileViewModel : ViewModelBase
{
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

    public ProfileViewModel()
    {
        _avatarBytes = SettingsStore.LoadAvatar();
        if (_avatarBytes != null)
        {
            LoadBitmap(_avatarBytes);
        }
    }

    /// <summary>
    /// Сохранить профиль. Кнопка фиксирует состояние страницы целиком — и имя
    /// с описанием, и аватар: иначе выбор картинки записывался бы сразу, а
    /// имя по кнопке, и было бы неясно, что уже сохранено, а что нет.
    /// </summary>
    [RelayCommand]
    private async System.Threading.Tasks.Task Save()
    {
        SettingsStore.Current.UserName = Name;
        SettingsStore.Current.Bio = Bio;
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
    }

    [RelayCommand]
    private void RemoveAvatar()
    {
        _avatarBytes = null;
        AvatarImage = null;
    }

    private void LoadBitmap(byte[] bytes)
    {
        try
        {
            using var ms = new MemoryStream(bytes);
            AvatarImage = new Bitmap(ms);
        }
        catch (System.Exception)
        {
            // Файл на диске оказался не картинкой (или повреждён) — показываем
            // заглушку вместо аватара, а не роняем страницу профиля.
            _avatarBytes = null;
            AvatarImage = null;
        }
    }
}
