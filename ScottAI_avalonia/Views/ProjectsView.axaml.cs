using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Markup.Xaml;
using Avalonia.Platform.Storage;
using ScottAI.Avalonia.ViewModels;

namespace ScottAI.Avalonia.Views;

/// <summary>
/// Раздел «Проекты».
///
/// Своей логики почти нет — кроме выбора папки: окно выбора живёт у окна
/// программы, и добраться до него из модели нечем. Печатать путь руками тоже
/// можно, но по памяти его никто не помнит.
/// </summary>
public partial class ProjectsView : UserControl
{
    public ProjectsView()
    {
        InitializeComponent();
    }

    private void InitializeComponent() => AvaloniaXamlLoader.Load(this);

    private async void OnPickFolderClick(object? sender, RoutedEventArgs e)
    {
        var окно = TopLevel.GetTopLevel(this);
        if (окно?.StorageProvider is null || DataContext is not ProjectsViewModel vm)
        {
            return;
        }

        var папки = await окно.StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
        {
            Title = "Папка с проектом",
            AllowMultiple = false,
        });

        if (папки.Count > 0)
        {
            vm.NewPath = папки[0].Path.LocalPath;
        }
    }
}
