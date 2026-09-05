using Avalonia.Controls;
using ScottAI.Avalonia.Services;
using ScottAI.Avalonia.ViewModels;

namespace ScottAI.Avalonia;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();

        // Backend, поднятый лаунчером, гасится вместе с окном: иначе после
        // закрытия он остался бы висеть, занимая порт 8000 и видеокарту, а при
        // следующем запуске новый экземпляр не смог бы открыть порт.
        Closing += (_, _) => (DataContext as ViewModels.MainWindowViewModel)?.ShutdownBackend();
        DataContext = new MainWindowViewModel();

        ThemeService.StyleApplied += OnStyleApplied;
        ApplyTransparency(ThemeService.CurrentStyle);
        ItemsStagger.Attach(ToastHost);
    }

    private void OnStyleApplied(AppStyle style) => ApplyTransparency(style);

    /// <summary>
    /// Настоящий блюр рабочего стола (не имитация цветом) только для Glass —
    /// Avalonia сама владеет WinAPI-хендлом окна, поэтому TransparencyLevelHint
    /// работает надёжно (в отличие от прошлой попытки на Rust/Slint через
    /// window_vibrancy, где не было прямого доступа к хендлу). Для Classic и
    /// Terminal Pro держим None — не платим за композитинг там, где фон и так
    /// полностью непрозрачный.
    /// </summary>
    private void ApplyTransparency(AppStyle style)
    {
        TransparencyLevelHint = style == AppStyle.Glass
            ? new[] { WindowTransparencyLevel.AcrylicBlur, WindowTransparencyLevel.Blur, WindowTransparencyLevel.Transparent }
            : new[] { WindowTransparencyLevel.None };
    }
}
