using Avalonia.Controls;
using ScottAI.Avalonia.Services;
using ScottAI.Avalonia.ViewModels;

namespace ScottAI.Avalonia;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();

        // Закрытие окна при включённом фоновом режиме прячет Scott в область
        // уведомлений, а не завершает его: смысл голосового ассистента в том,
        // чтобы услышать обращение тогда, когда окно давно закрыто. Выйти
        // по-настоящему можно из меню иконки в трее — там же гасится backend.
        //
        // Если фоновый режим выключен, поведение прежнее: закрыли окно —
        // остановили и backend, иначе он висел бы, занимая порт и видеокарту.
        Closing += (sender, e) =>
        {
            if (Services.SettingsStore.Current.RunInBackground)
            {
                e.Cancel = true;
                Hide();
                return;
            }

            (DataContext as ViewModels.MainWindowViewModel)?.ShutdownBackend();
            // global:: обязателен: пространство имён проекта тоже начинается с
            // «ScottAI.Avalonia», и без него компилятор ищет Application внутри него.
            if (global::Avalonia.Application.Current?.ApplicationLifetime
                is global::Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime desktop)
            {
                desktop.Shutdown();
            }
        };
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
