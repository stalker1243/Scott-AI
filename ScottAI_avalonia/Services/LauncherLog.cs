using System;
using System.IO;
using System.Text;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// Журнал самого лаунчера.
///
/// Заведён после случая, когда программа переставала запускаться совсем:
/// человек нажимал ярлык, и ничего не происходило — ни окна, ни сообщения.
/// Причина (не нашёлся ресурс после переименования сборки) была видна только
/// изнутри, а снаружи не оставалось ни следа.
///
/// Файл лежит рядом с настройками, в папке пользователя: программа может быть
/// установлена туда, где ей не разрешено писать, а сюда — всегда.
/// </summary>
public static class LauncherLog
{
    private static readonly object Lock = new();

    public static string Directory { get; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "ScottAI", "logs");

    public static string FilePath { get; } = Path.Combine(Directory, "launcher.log");

    /// <summary>Записать строку в журнал. Ошибки записи проглатываются:
    /// падать из-за журнала — последнее, чего можно хотеть.</summary>
    public static void Write(string message)
    {
        try
        {
            lock (Lock)
            {
                System.IO.Directory.CreateDirectory(Directory);
                TrimIfHuge();

                var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss}  {message}{Environment.NewLine}";
                File.AppendAllText(FilePath, line, Encoding.UTF8);
            }
        }
        catch (Exception)
        {
            // Некуда писать — значит некуда.
        }
    }

    /// <summary>Записать исключение целиком: тип, сообщение и стек.</summary>
    public static void WriteError(string context, Exception error)
    {
        Write($"ОШИБКА: {context}");
        Write($"  {error.GetType().Name}: {error.Message}");

        if (!string.IsNullOrWhiteSpace(error.StackTrace))
        {
            Write("  " + error.StackTrace.Replace(Environment.NewLine, Environment.NewLine + "  "));
        }

        if (error.InnerException is not null)
        {
            Write($"  причина: {error.InnerException.GetType().Name}: {error.InnerException.Message}");
        }
    }

    /// <summary>
    /// Не давать журналу расти без предела.
    ///
    /// Он пишется при каждом запуске, а живёт годами: без обрезки файл однажды
    /// стал бы больше самой программы.
    /// </summary>
    private static void TrimIfHuge()
    {
        try
        {
            var file = new FileInfo(FilePath);
            if (!file.Exists || file.Length < 512 * 1024)
            {
                return;
            }

            var lines = File.ReadAllLines(FilePath);
            var keep = lines.Length > 500 ? lines[^500..] : lines;
            File.WriteAllLines(FilePath, keep, Encoding.UTF8);
        }
        catch (Exception)
        {
            // Не получилось обрезать — не беда.
        }
    }
}
