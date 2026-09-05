using System;
using System.IO;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using ScottAI.Avalonia.ViewModels;

namespace ScottAI.Avalonia.Views;

public partial class ProfileView : UserControl
{
    private bool _dragging;
    private Point _lastPointer;

    public ProfileView()
    {
        InitializeComponent();
    }

    private async void OnPickAvatarClick(object? sender, RoutedEventArgs e)
    {
        var topLevel = TopLevel.GetTopLevel(this);
        if (topLevel?.StorageProvider is null) return;

        var files = await topLevel.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Выберите фото",
            AllowMultiple = false,
            FileTypeFilter = new[] { FilePickerFileTypes.ImageAll },
        });
        if (files.Count == 0) return;

        try
        {
            await using var stream = await files[0].OpenReadAsync();
            using var ms = new MemoryStream();
            await stream.CopyToAsync(ms);
            if (DataContext is ProfileViewModel vm)
                vm.SetAvatarFromBytes(ms.ToArray());
        }
        catch
        {
            // тихо игнорируем — неподдерживаемый/повреждённый файл изображения
        }
    }

    // ==================== Подбор кадра ====================
    //
    // Перетаскивание живёт здесь, а не во ViewModel, потому что ему нужны
    // события указателя и захват мыши. Наружу уходит только смещение в
    // пикселях — им ViewModel и распоряжается.

    private void OnCropPressed(object? sender, PointerPressedEventArgs e)
    {
        if (DataContext is not ProfileViewModel vm || !vm.HasAvatar) return;

        _dragging = true;
        _lastPointer = e.GetPosition(this);
        e.Pointer.Capture(sender as IInputElement);
    }

    private void OnCropMoved(object? sender, PointerEventArgs e)
    {
        if (!_dragging || DataContext is not ProfileViewModel vm) return;

        var position = e.GetPosition(this);
        vm.DragAvatar(position.X - _lastPointer.X, position.Y - _lastPointer.Y);
        _lastPointer = position;
    }

    private void OnCropReleased(object? sender, PointerReleasedEventArgs e)
    {
        _dragging = false;
        e.Pointer.Capture(null);
    }

    private void OnCropWheel(object? sender, PointerWheelEventArgs e)
    {
        if (DataContext is not ProfileViewModel vm || !vm.HasAvatar) return;

        // Шаг подобран так, чтобы одного щелчка колеса хватало на заметное, но
        // не резкое изменение — иначе подобрать кадр мышью почти невозможно.
        vm.ZoomAvatar(e.Delta.Y * 0.1);
        e.Handled = true;
    }
}
