using System;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using ScottAI.Avalonia.Services;
using ScottAI.Avalonia.ViewModels;

namespace ScottAI.Avalonia;

public partial class App : Application
{
    public override void Initialize()
    {
        AvaloniaXamlLoader.Load(this);
    }

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            // Оформление восстанавливается до создания окна: иначе оно успело бы
            // отрисоваться в стиле по умолчанию и на глазах перекраситься.
            ThemeService.ApplySaved(SettingsStore.Current);
            desktop.MainWindow = new MainWindow();
            // Иконка ставится ПОСЛЕ создания окна: до этого момента её просто
            // некуда применять — MainWindow ещё не существует.
            AppIconService.Apply(SettingsStore.Current.IconVariant);

            // Закрытие окна не должно завершать приложение, пока включён
            // фоновый режим: Scott продолжает слушать, а окно прячется в трей.
            // Выйти по-настоящему можно из меню иконки.
            desktop.ShutdownMode = ShutdownMode.OnExplicitShutdown;
        }

        base.OnFrameworkInitializationCompleted();
    }

    private Window? MainWindowOrNull =>
        (ApplicationLifetime as IClassicDesktopStyleApplicationLifetime)?.MainWindow;

    /// <summary>Щелчок по иконке — показать окно, если оно спрятано.</summary>
    private void OnTrayClicked(object? sender, EventArgs e) => ShowMainWindow();

    private void OnTrayShow(object? sender, EventArgs e) => ShowMainWindow();

    private void ShowMainWindow()
    {
        var window = MainWindowOrNull;
        if (window is null) return;

        window.Show();
        window.WindowState = WindowState.Normal;
        window.Activate();
    }

    /// <summary>
    /// Выход по-настоящему: остановить backend и закрыть приложение.
    ///
    /// Единственный способ завершить Scott, когда включён фоновый режим, —
    /// поэтому здесь важно не забыть про backend, иначе он останется висеть,
    /// занимая порт и видеокарту.
    /// </summary>
    private void OnTrayExit(object? sender, EventArgs e)
    {
        (MainWindowOrNull?.DataContext as MainWindowViewModel)?.ShutdownBackend();

        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            desktop.Shutdown();
        }
    }
}
