using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// Запуск backend вместе с лаунчером.
///
/// До этого backend приходилось поднимать вручную в терминале, и без него
/// лаунчер показывал «offline» — человек, поставивший программу впервые,
/// решал, что она сломана. Теперь лаунчер проверяет, отвечает ли backend, и
/// если нет — запускает его сам.
///
/// Два правила, которые здесь важнее удобства:
///
/// * **Чужой процесс не трогаем.** Если backend уже отвечает, значит его
///   запустили до нас — возможно, разработчик в терминале, чтобы видеть логи.
///   Останавливать при выходе мы будем только то, что запустили сами.
/// * **Молча не падаем.** Не нашёлся Python, не оказалось main.py, процесс
///   умер на старте — об этом нужно сказать словами, а не оставить вечное
///   «offline», за которым непонятно что.
/// </summary>
public class BackendLauncher
{
    private Process? _process;

    /// <summary>Что сейчас происходит — лаунчер показывает это пользователю.</summary>
    public string Status { get; private set; } = "";

    /// <summary>Запустил ли backend именно этот лаунчер (а не человек до него).</summary>
    public bool StartedByUs => _process is { HasExited: false };

    /// <summary>
    /// Убедиться, что backend работает: проверить и при необходимости запустить.
    /// </summary>
    public async Task<(bool Success, string Message)> EnsureRunningAsync(BackendClient client)
    {
        if (await client.HealthAsync())
        {
            Status = "backend уже работает";
            return (true, Status);
        }

        var backendDir = FindBackendDirectory();
        if (backendDir is null)
        {
            Status = "не нашёл папку backend рядом с лаунчером";
            return (false, Status);
        }

        var python = FindPython();
        if (python is null)
        {
            Status = "не нашёл Python — установите Python 3.13 и добавьте его в PATH";
            return (false, Status);
        }

        try
        {
            _process = Process.Start(new ProcessStartInfo
            {
                FileName = python.Value.File,
                // Префикс версии сохраняется: если Python нашёлся как «py -3.13»,
                // запускать нужно тем же способом, иначе py возьмёт версию по
                // умолчанию — а она может оказаться другой.
                //
                // -u выключает буферизацию: иначе сообщения backend оседают в
                // буфере и в случае падения не видно, на чём он остановился.
                Arguments = $"{python.Value.Prefix}-u main.py".TrimStart(),
                WorkingDirectory = backendDir,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                // Backend завершится сам, если лаунчер исчезнет. Штатный выход
                // гасит его и без этого, но через диспетчер задач процесс
                // убивают жёстко — и backend оставался сиротой, держа порт и
                // видеокарту, пока пользователь считал, что вышел из программы.
                Environment = { ["SCOTT_PARENT_PID"] = Environment.ProcessId.ToString() },
            });
        }
        catch (Exception e)
        {
            Status = $"не удалось запустить backend: {e.Message}";
            return (false, Status);
        }

        if (_process is null)
        {
            Status = "процесс backend не запустился";
            return (false, Status);
        }

        // Вывод обязательно вычитывается, иначе буфер канала переполнится и
        // backend встанет намертво где-то в середине запуска.
        _ = Task.Run(() => DrainOutput(_process));

        Status = "запускаю Scott…";
        return await WaitUntilReadyAsync(client);
    }

    /// <summary>
    /// Дождаться готовности.
    ///
    /// Ждать приходится долго: при первом запуске backend поднимает Whisper и
    /// Silero, а если моделей ещё нет в кэше — скачивает их. Поэтому минута, а
    /// не пять секунд, как кажется разумным по привычке.
    /// </summary>
    private async Task<(bool Success, string Message)> WaitUntilReadyAsync(BackendClient client)
    {
        var deadline = DateTime.UtcNow.AddSeconds(60);

        while (DateTime.UtcNow < deadline)
        {
            if (_process is { HasExited: true })
            {
                Status = $"backend завершился сразу после запуска (код {_process.ExitCode})";
                return (false, Status);
            }

            if (await client.HealthAsync())
            {
                Status = "backend запущен";
                return (true, Status);
            }

            await Task.Delay(700);
        }

        Status = "backend не ответил за минуту — посмотрите вкладку «Логи»";
        return (false, Status);
    }

    /// <summary>
    /// Остановить backend, если его запускали мы.
    ///
    /// Процесс, поднятый человеком в терминале, не трогаем: он мог оставить его
    /// нарочно, чтобы читать логи, и убивать чужое при закрытии окна — грубо.
    /// </summary>
    public void StopIfOurs()
    {
        if (_process is null || _process.HasExited) return;

        try
        {
            _process.Kill(entireProcessTree: true);
            _process.WaitForExit(3000);
        }
        catch (Exception e)
        {
            Console.Error.WriteLine($"Не удалось остановить backend: {e.Message}");
        }
    }

    private static void DrainOutput(Process process)
    {
        try
        {
            while (!process.StandardOutput.EndOfStream)
            {
                process.StandardOutput.ReadLine();
            }
        }
        catch
        {
            // Процесс закрылся — читать больше нечего.
        }
    }

    /// <summary>
    /// Найти папку backend.
    ///
    /// Лаунчер запускается из bin/Debug/net10.0, поэтому ищем вверх по дереву —
    /// тем же приёмом, которым EnvConfig находит .env.
    /// </summary>
    internal static string? FindBackendDirectory()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);

        while (dir != null)
        {
            var candidate = Path.Combine(dir.FullName, "backend");
            if (File.Exists(Path.Combine(candidate, "main.py")))
            {
                return candidate;
            }
            dir = dir.Parent;
        }

        return null;
    }

    /// <summary>
    /// Найти подходящий Python.
    ///
    /// Порядок не случаен: сначала спрашиваем у py-лаунчера конкретную версию,
    /// потому что на машине их обычно несколько, а backend рассчитан на 3.13.
    /// Виртуальные окружения проекта намеренно не используются — библиотеки
    /// ставятся в системный Python.
    /// </summary>
    internal static (string File, string Prefix)? FindPython()
    {
        foreach (var (file, prefix) in Candidates())
        {
            if (Probe(file, $"{prefix}--version".TrimStart()))
            {
                return (file, prefix);
            }
        }
        return null;
    }

    /// <summary>
    /// Чем пробовать запускать, по порядку.
    ///
    /// Prefix — то, что нужно передать перед аргументами скрипта. У py-лаунчера
    /// это версия: на машине обычно несколько Python, а backend рассчитан на
    /// 3.13, и без явного указания py возьмёт версию по умолчанию.
    /// </summary>
    private static IEnumerable<(string File, string Prefix)> Candidates()
    {
        // Встроенный Python из дистрибутива — первым. На чужой машине его
        // может не быть в PATH вовсе, а лаунчер отвечал «не нашёл Python»,
        // хотя интерпретатор лежал в соседней папке. Именно в него мастер
        // первого запуска ставит torch и модели, поэтому системный Python,
        // даже если он есть, здесь ни при чём.
        var bundled = FindBundledPython();
        if (bundled is not null)
        {
            yield return (bundled, "");
        }

        if (OperatingSystem.IsWindows())
        {
            yield return ("py", "-3.13 ");
            yield return ("python", "");
        }
        else
        {
            yield return ("python3.13", "");
            yield return ("python3", "");
            yield return ("python", "");
        }
    }

    /// <summary>
    /// Python, положенный рядом установщиком: папка runtime возле программы.
    ///
    /// Ищется вверх от папки программы, как и backend: лаунчер лежит в
    /// подпапке launcher, а runtime — рядом с ней.
    /// </summary>
    private static string? FindBundledPython()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);

        while (dir != null)
        {
            var candidate = Path.Combine(dir.FullName, "runtime",
                OperatingSystem.IsWindows() ? "python.exe" : "bin/python3");
            if (File.Exists(candidate))
            {
                return candidate;
            }
            dir = dir.Parent;
        }

        return null;
    }

    private static bool Probe(string file, string args)
    {
        try
        {
            using var probe = Process.Start(new ProcessStartInfo
            {
                FileName = file,
                Arguments = args,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            });

            if (probe is null) return false;
            probe.WaitForExit(4000);
            return probe.HasExited && probe.ExitCode == 0;
        }
        catch
        {
            return false;
        }
    }
}
