using System;
using System.IO;
using System.Text.Json;
using ScottAI.Mobile.Models;

namespace ScottAI.Mobile.Services;

/// <summary>
/// Настройки на устройстве.
///
/// Файл, а не хранилище платформы: одинаково работает и на телефоне, и в окне
/// на компьютере, где приложение отлаживается. Разные пути к данным на каждой
/// платформе — первое, обо что спотыкаются такие приложения, и разбираться с
/// этим ради трёх полей незачем.
/// </summary>
public static class SettingsStore
{
    private static readonly string Папка = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "ScottAI");

    private static readonly string Файл = Path.Combine(Папка, "settings.json");

    private static AppSettings? _кэш;

    public static AppSettings Current => _кэш ??= Load();

    private static AppSettings Load()
    {
        try
        {
            if (File.Exists(Файл))
            {
                var прочитано = JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(Файл));
                if (прочитано is not null)
                {
                    return прочитано;
                }
            }
        }
        catch
        {
            // Испорченный файл означает «настроек нет», а не отказ запуститься:
            // приложение откроется с умолчаниями и предложит привязаться заново.
        }

        return new AppSettings();
    }

    public static void Save()
    {
        try
        {
            Directory.CreateDirectory(Папка);
            File.WriteAllText(Файл, JsonSerializer.Serialize(Current,
                new JsonSerializerOptions { WriteIndented = true }));
        }
        catch
        {
            // Не сохранилось — приложение продолжает работать с тем, что в
            // памяти. Ронять его из-за настроек нельзя.
        }
    }

    /// <summary>Забыть привязку. Внешний вид остаётся: его выбирал человек.</summary>
    public static void Unpair()
    {
        Current.Token = "";
        Current.Host = "";
        Current.DeviceName = "";
        Save();
    }
}
