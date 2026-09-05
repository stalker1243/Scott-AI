using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace ScottAI.Avalonia.Services;

/// <summary>Одно событие установки: что делается и насколько продвинулись.</summary>
public readonly record struct SetupProgress(string Message, double Fraction);

/// <summary>
/// Подготовка машины при первом запуске: тяжёлые библиотеки и модели речи.
///
/// В дистрибутив они не входят намеренно — torch со сборкой под видеокарту
/// весит около четырёх гигабайт, и правильная сборка зависит от того, есть ли
/// в машине видеокарта NVIDIA. Такой архив никто не стал бы скачивать, и
/// половине машин он достался бы неверным.
///
/// Всю работу делает backend/bootstrap.py — здесь только запуск и чтение его
/// вывода. Разделение не случайно: ту же подготовку запускает установщик, и
/// логика должна быть одна, а не две расходящиеся.
/// </summary>
public sealed class SetupService
{
    /// <summary>Готова ли машина и какая в ней видеокарта.</summary>
    public readonly record struct Readiness(bool Ready, string? Gpu, string? Error);

    /// <summary>
    /// Нужна ли подготовка.
    ///
    /// Ответ читается по коду возврата, а не по тексту: bootstrap специально
    /// возвращает 0 для готовой машины и 2 для неготовой.
    /// </summary>
    public async Task<Readiness> CheckAsync(CancellationToken token = default)
    {
        var start = BuildStart("--check --json");
        if (start is null)
        {
            return new Readiness(false, null, "не нашёл Python или папку backend");
        }

        try
        {
            using var process = Process.Start(start);
            if (process is null)
            {
                return new Readiness(false, null, "не удалось запустить проверку");
            }

            string? gpu = null;
            bool ready = false;

            while (await process.StandardOutput.ReadLineAsync(token) is { } line)
            {
                var payload = Parse(line);
                if (payload is null || GetString(payload.Value, "type") != "check")
                {
                    continue;
                }

                ready = payload.Value.TryGetProperty("ready", out var readyValue)
                        && readyValue.ValueKind == JsonValueKind.True;
                gpu = GetString(payload.Value, "gpu");
            }

            await process.WaitForExitAsync(token);
            return new Readiness(ready, gpu, null);
        }
        catch (Exception e)
        {
            return new Readiness(false, null, e.Message);
        }
    }

    /// <summary>
    /// Поставить всё недостающее, докладывая о ходе работы.
    ///
    /// Занимает минуты: torch скачивается гигабайтами, модели — сотнями
    /// мегабайт. Поэтому события идут потоком, а не одним ответом в конце.
    /// </summary>
    public async Task<(bool Success, string Error)> RunAsync(
        IProgress<SetupProgress> progress, CancellationToken token = default)
    {
        var start = BuildStart("--json");
        if (start is null)
        {
            return (false, "не нашёл Python или папку backend");
        }

        try
        {
            using var process = Process.Start(start);
            if (process is null)
            {
                return (false, "не удалось запустить подготовку");
            }

            var error = "";

            while (await process.StandardOutput.ReadLineAsync(token) is { } line)
            {
                var payload = Parse(line);
                if (payload is null)
                {
                    continue;
                }

                switch (GetString(payload.Value, "type"))
                {
                    case "progress":
                        var fraction = payload.Value.TryGetProperty("fraction", out var f)
                            ? f.GetDouble() : 0;
                        progress.Report(new SetupProgress(
                            GetString(payload.Value, "message") ?? "", fraction));
                        break;

                    case "error":
                        error = GetString(payload.Value, "message") ?? "неизвестная ошибка";
                        break;
                }
            }

            await process.WaitForExitAsync(token);

            if (process.ExitCode != 0)
            {
                // Хвост stderr пригодится, когда bootstrap упал раньше, чем
                // успел сообщить о причине словами.
                var tail = await process.StandardError.ReadToEndAsync(token);
                return (false, string.IsNullOrWhiteSpace(error) ? Shorten(tail) : error);
            }

            return (true, "");
        }
        catch (OperationCanceledException)
        {
            return (false, "подготовка отменена");
        }
        catch (Exception e)
        {
            return (false, e.Message);
        }
    }

    private static ProcessStartInfo? BuildStart(string arguments)
    {
        var backendDir = BackendLauncher.FindBackendDirectory();
        var python = BackendLauncher.FindPython();
        if (backendDir is null || python is null)
        {
            return null;
        }

        var info = new ProcessStartInfo
        {
            FileName = python.Value.File,
            Arguments = $"{python.Value.Prefix}-u bootstrap.py {arguments}".TrimStart(),
            WorkingDirectory = backendDir,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };

        // Вывод bootstrap содержит русский текст: без явной кодировки в
        // сообщениях приходят кракозябры.
        info.StandardOutputEncoding = System.Text.Encoding.UTF8;
        info.StandardErrorEncoding = System.Text.Encoding.UTF8;
        info.Environment["PYTHONIOENCODING"] = "utf-8";
        return info;
    }

    private static JsonElement? Parse(string line)
    {
        line = line.Trim();
        if (line.Length == 0 || line[0] != '{')
        {
            // Библиотеки иногда печатают в stdout своё — на такие строки
            // просто не обращаем внимания.
            return null;
        }

        try
        {
            return JsonDocument.Parse(line).RootElement.Clone();
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static string? GetString(JsonElement element, string name)
        => element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private static string Shorten(string text)
    {
        text = text.Trim();
        if (text.Length == 0)
        {
            return "подготовка завершилась с ошибкой";
        }

        var lines = new List<string>(text.Split('\n', StringSplitOptions.RemoveEmptyEntries));
        var tail = lines.GetRange(Math.Max(0, lines.Count - 4), Math.Min(4, lines.Count));
        return string.Join("\n", tail).Trim();
    }
}
