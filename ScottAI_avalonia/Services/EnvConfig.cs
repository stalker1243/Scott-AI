using System;
using System.Collections.Generic;
using System.IO;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// Мини-читалка .env — тот же файл (neyro/.env), который backend читает через
/// python-dotenv. Ищет вверх от рабочей директории, как это делает
/// load_dotenv() без аргументов на стороне backend, чтобы оба процесса видели
/// один и тот же EXECUTE_TOKEN для доступа к защищённым эндпоинтам
/// (/kill-process и т.п.) без дублирования секрета где-то ещё.
/// </summary>
public static class EnvConfig
{
    private static Dictionary<string, string>? _cache;

    public static string? Get(string key)
    {
        _cache ??= Load();
        return _cache.TryGetValue(key, out var value) ? value : null;
    }

    private static Dictionary<string, string> Load()
    {
        var result = new Dictionary<string, string>();
        var dir = new DirectoryInfo(AppContext.BaseDirectory);

        while (dir != null)
        {
            var candidate = Path.Combine(dir.FullName, ".env");
            if (File.Exists(candidate))
            {
                foreach (var line in File.ReadAllLines(candidate))
                {
                    var trimmed = line.Trim();
                    if (trimmed.Length == 0 || trimmed.StartsWith("#")) continue;
                    var idx = trimmed.IndexOf('=');
                    if (idx <= 0) continue;
                    var key = trimmed[..idx].Trim();
                    var value = trimmed[(idx + 1)..].Trim();
                    result[key] = value;
                }
                break;
            }
            dir = dir.Parent;
        }

        return result;
    }
}
