using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using ScottAI.Avalonia.Services;

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
        }

        base.OnFrameworkInitializationCompleted();
    }
}