using System;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace ScottAI.Avalonia.Services;

/// <summary>Что backend знает о вышедшей версии.</summary>
public sealed record UpdateInfo(
    bool Available,
    string CurrentVersion,
    string LatestVersion,
    string Notes,
    string DownloadUrl,
    string AssetName,
    long AssetSize,
    string ReleaseUrl,
    string Error);

/// <summary>
/// Обновления: спросить у backend и скачать установщик.
///
/// Проверку делает backend (`/api/version/update-check`) — он же читает
/// VERSION.json и ходит на GitHub, и дублировать эту логику в лаунчере значило
/// бы иметь две расходящиеся версии правды. Лаунчеру остаётся показать
/// человеку, что вышло, и — по его слову — скачать и запустить установщик.
/// </summary>
public sealed class UpdateService
{
    private readonly HttpClient _http;

    public UpdateService(HttpClient? http = null)
    {
        // Отдельный клиент с большим таймаутом: установщик весит десятки
        // мегабайт, а общий клиент лаунчера настроен на короткие запросы.
        _http = http ?? new HttpClient { Timeout = TimeSpan.FromMinutes(30) };
    }

    public async Task<UpdateInfo?> CheckAsync(string backendBase, bool force = false,
                                              CancellationToken token = default)
    {
        try
        {
            var url = $"{backendBase.TrimEnd('/')}/api/version/update-check?force={(force ? "true" : "false")}";
            using var response = await _http.GetAsync(url, token);
            if (!response.IsSuccessStatusCode)
            {
                return null;
            }

            await using var stream = await response.Content.ReadAsStreamAsync(token);
            using var document = await JsonDocument.ParseAsync(stream, cancellationToken: token);

            if (!document.RootElement.TryGetProperty("data", out var data))
            {
                return null;
            }

            return new UpdateInfo(
                Available: Flag(data, "update_available"),
                CurrentVersion: Text(data, "current_version"),
                LatestVersion: Text(data, "latest_version"),
                Notes: Text(data, "release_notes"),
                DownloadUrl: Text(data, "download_url"),
                AssetName: Text(data, "asset_name"),
                AssetSize: Number(data, "asset_size"),
                ReleaseUrl: Text(data, "release_url"),
                Error: Text(data, "error"));
        }
        catch (Exception)
        {
            // Backend не поднялся, сеть отвалилась — обновление подождёт до
            // следующего запуска. Ронять из-за этого лаунчер нельзя.
            return null;
        }
    }

    /// <summary>
    /// Скачать установщик во временную папку, докладывая о ходе загрузки.
    ///
    /// Возвращает путь к файлу или пустую строку с текстом ошибки.
    /// </summary>
    public async Task<(string Path, string Error)> DownloadAsync(
        UpdateInfo info, IProgress<double> progress, CancellationToken token = default)
    {
        if (string.IsNullOrWhiteSpace(info.DownloadUrl))
        {
            return ("", "у этого выпуска нет готового установщика");
        }

        var name = string.IsNullOrWhiteSpace(info.AssetName)
            ? $"ScottAI-{info.LatestVersion}-setup.exe"
            : info.AssetName;
        var target = Path.Combine(Path.GetTempPath(), name);

        try
        {
            using var response = await _http.GetAsync(
                info.DownloadUrl, HttpCompletionOption.ResponseHeadersRead, token);
            response.EnsureSuccessStatusCode();

            // Размер берётся из ответа, а не из данных релиза: ссылка ведёт
            // через редирект, и настоящий размер известен только здесь.
            var total = response.Content.Headers.ContentLength ?? info.AssetSize;

            await using var source = await response.Content.ReadAsStreamAsync(token);
            await using var file = File.Create(target);

            var buffer = new byte[81920];
            long done = 0;
            int read;

            while ((read = await source.ReadAsync(buffer, token)) > 0)
            {
                await file.WriteAsync(buffer.AsMemory(0, read), token);
                done += read;

                if (total > 0)
                {
                    progress.Report(Math.Clamp((double)done / total, 0, 1));
                }
            }

            return (target, "");
        }
        catch (OperationCanceledException)
        {
            TryDelete(target);
            return ("", "загрузка отменена");
        }
        catch (Exception e)
        {
            TryDelete(target);
            return ("", e.Message);
        }
    }

    private static void TryDelete(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch (IOException)
        {
            // Недокачанный файл остался в %TEMP% — Windows приберёт его сама.
        }
    }

    private static string Text(JsonElement element, string name)
        => element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? ""
            : "";

    private static bool Flag(JsonElement element, string name)
        => element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.True;

    private static long Number(JsonElement element, string name)
        => element.TryGetProperty(name, out var value) && value.TryGetInt64(out var number) ? number : 0;
}
