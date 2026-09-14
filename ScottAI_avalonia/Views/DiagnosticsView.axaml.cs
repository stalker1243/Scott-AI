using Avalonia.Controls;
using Avalonia.Input.Platform;
using Avalonia.Interactivity;
using Avalonia.Markup.Xaml;
using ScottAI.Avalonia.Services;
using ScottAI.Avalonia.ViewModels;

namespace ScottAI.Avalonia.Views;

/// <summary>
/// Раздел «Диагностика».
///
/// Своей логики почти нет — кроме копирования отчёта: буфер обмена в Avalonia
/// живёт у окна, и добираться до него из модели пришлось бы окольным путём.
/// </summary>
public partial class DiagnosticsView : UserControl
{
    public DiagnosticsView()
    {
        InitializeComponent();
    }

    private void InitializeComponent() => AvaloniaXamlLoader.Load(this);

    private async void OnCopyReportClick(object? sender, RoutedEventArgs e)
    {
        if (DataContext is not DiagnosticsViewModel vm)
        {
            return;
        }

        var текст = await vm.BuildReportAsync();
        if (string.IsNullOrWhiteSpace(текст))
        {
            ToastService.Error("Не удалось собрать отчёт — backend не отвечает");
            return;
        }

        var буфер = TopLevel.GetTopLevel(this)?.Clipboard;
        if (буфер is null)
        {
            ToastService.Error("Буфер обмена недоступен");
            return;
        }

        await буфер.SetTextAsync(текст);
        await vm.ReportCopied();
    }
}
