using Avalonia;
using System;

namespace ScottAI.Avalonia;

class Program
{
    // Initialization code. Don't use any Avalonia, third-party APIs or any
    // SynchronizationContext-reliant code before AppMain is called: things aren't initialized
    // yet and stuff might break.
    [STAThread]
    public static void Main(string[] args)
    {
        // Журнал запуска. Заведён после случая, когда программа переставала
        // открываться совсем: ярлык нажат, окна нет, и ни следа о причине.
        // Теперь причина всегда остаётся в файле — его же кладут в отчёт о
        // проблеме.
        Services.LauncherLog.Write($"запуск ScottAI, версия сборки {typeof(Program).Assembly.GetName().Version}");

        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            if (e.ExceptionObject is Exception error)
            {
                Services.LauncherLog.WriteError("необработанная ошибка", error);
            }
        };

        System.Threading.Tasks.TaskScheduler.UnobservedTaskException += (_, e) =>
        {
            Services.LauncherLog.WriteError("ошибка в фоновой задаче", e.Exception);
            e.SetObserved();
        };

        try
        {
            BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
        }
        catch (Exception error)
        {
            // Падение до появления окна — самый неприятный случай: снаружи
            // выглядит как «ничего не произошло». Записываем и выходим с
            // ненулевым кодом, чтобы это было видно и запускающей стороне.
            Services.LauncherLog.WriteError("не удалось запустить программу", error);
            Environment.ExitCode = 1;
        }
    }

    // Avalonia configuration, don't remove; also used by visual designer.
    public static AppBuilder BuildAvaloniaApp()
        => AppBuilder.Configure<App>()
            .UsePlatformDetect()
#if DEBUG
            .WithDeveloperTools()
#endif
            .WithInterFont()
            .LogToTrace();
}
