using Avalonia.Controls;
using Avalonia.Input.Platform;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;
using ScottAI.Avalonia.ViewModels;

namespace ScottAI.Avalonia.Views;

public partial class ChatView : UserControl
{
    public ChatView()
    {
        InitializeComponent();

        // Фокус в поле ввода сразу при открытии чата: иначе человек печатает
        // «в никуда», а Enter не срабатывает — клавиши просто некуда девать.
        AttachedToVisualTree += (_, _) => Input.Focus();
    }

    /// <summary>
    /// Копирование блока кода в буфер обмена.
    ///
    /// Обработчик, а не команда во ViewModel: буфер обмена в Avalonia живёт у
    /// окна (TopLevel), и добираться до него из ViewModel пришлось бы окольным
    /// путём.
    /// </summary>
    private async void OnCopyCodeClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button button || button.DataContext is not MessageSegment segment)
            return;

        var clipboard = TopLevel.GetTopLevel(this)?.Clipboard;
        if (clipboard is null)
        {
            ToastService.Error("Буфер обмена недоступен");
            return;
        }

        await clipboard.SetTextAsync(segment.Text);
        ToastService.Success("Код скопирован");
    }

    private async void OnPickImageClick(object? sender, RoutedEventArgs e)
    {
        var topLevel = TopLevel.GetTopLevel(this);
        if (topLevel?.StorageProvider is null) return;

        var files = await topLevel.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Выберите изображение",
            AllowMultiple = false,
            FileTypeFilter = new[] { FilePickerFileTypes.ImageAll },
        });
        if (files.Count == 0) return;

        if (DataContext is ChatViewModel vm)
            vm.SetAttachedImage(files[0].Name);
    }

    private async void OnPickFileClick(object? sender, RoutedEventArgs e)
    {
        var topLevel = TopLevel.GetTopLevel(this);
        if (topLevel?.StorageProvider is null) return;

        var files = await topLevel.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Выберите файл",
            AllowMultiple = false,
        });
        if (files.Count == 0) return;

        if (DataContext is ChatViewModel vm)
            vm.SetAttachedFile(files[0].Name);
    }
}
