using System;
using System.IO;
using System.Text;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// Всё, что Scott говорит о себе, — в файл.
///
/// ЗАЧЕМ. Backend печатает о себе через обычный вывод: какие модели прогрел, на
/// каком устройстве работает, что не смог и на чём споткнулся. Этот вывод
/// уходит в трубу к лаунчеру, и тот его вычитывал и ВЫБРАСЫВАЛ — читать было
/// обязательно (непрочитанная труба переполняется и вешает backend), а хранить
/// никто не догадался.
///
/// Стоило это целого разбирательства: 18 сентября Scott умер посреди проверки,
/// и выяснить причину оказалось нечем. В журнале ошибок пусто — туда попадает
/// только то, что идёт через logging, а Scott пишет о себе print'ом. Остались
/// лишь замеры, обрывающиеся на середине, и жалобы человека вслух: «по ходу,
/// бакенд окончательно отвалился».
///
/// Теперь остаётся след. Файл лежит рядом с журналом лаунчера и подрезается по
/// размеру: он нужен, чтобы посмотреть последние минуты жизни, а не хранить
/// историю за месяц.
/// </summary>
public static class BackendOutputLog
{
    private static readonly object Lock = new();

    public static string FilePath { get; } = Path.Combine(
        LauncherLog.Directory, "backend-output.log");

    /// <summary>Сколько держать. Больше — и файл начинает жить своей жизнью.</summary>
    private const long MaxBytes = 2 * 1024 * 1024;

    public static void Write(string line)
    {
        try
        {
            lock (Lock)
            {
                Directory.CreateDirectory(LauncherLog.Directory);
                TrimIfHuge();

                File.AppendAllText(
                    FilePath,
                    $"{DateTime.Now:HH:mm:ss}  {line}{Environment.NewLine}",
                    Encoding.UTF8);
            }
        }
        catch
        {
            // Падать из-за журнала — последнее, чего можно хотеть.
        }
    }

    /// <summary>Отметить в журнале, что backend завершился. Главная строка здесь.</summary>
    public static void NoteExit(int? exitCode)
    {
        Write(exitCode is null
            ? "=== backend завершился (код неизвестен) ==="
            : $"=== backend завершился, код {exitCode} ===");
    }

    private static void TrimIfHuge()
    {
        try
        {
            var файл = new FileInfo(FilePath);
            if (!файл.Exists || файл.Length <= MaxBytes)
            {
                return;
            }

            // Оставляем хвост: интересны всегда последние минуты, а не первые.
            var строки = File.ReadAllLines(FilePath);
            File.WriteAllLines(FilePath, строки[(строки.Length / 2)..], Encoding.UTF8);
        }
        catch
        {
            // Не вышло подрезать — переживём.
        }
    }
}
