using System.IO;
using Avalonia.Media.Imaging;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace ScottAI.Avalonia.ViewModels;

public partial class ProfileViewModel : ViewModelBase
{
    [ObservableProperty] private string _name = "";
    [ObservableProperty] private string _bio = "";
    [ObservableProperty] private bool _savedRecently;
    [ObservableProperty] private Bitmap? _avatarImage;

    [RelayCommand]
    private async System.Threading.Tasks.Task Save()
    {
        // TODO: постоянное хранение (как tauri-plugin-store в Tauri-версии) — пока только в памяти сессии.
        SavedRecently = true;
        await System.Threading.Tasks.Task.Delay(2000);
        SavedRecently = false;
    }

    /// <summary>Вызывается из code-behind View после выбора файла через StorageProvider (нужен доступ к TopLevel, поэтому сам пикер живёт в View).</summary>
    public void SetAvatarFromBytes(byte[] bytes)
    {
        using var ms = new MemoryStream(bytes);
        AvatarImage = new Bitmap(ms);
    }

    [RelayCommand]
    private void RemoveAvatar() => AvatarImage = null;
}
