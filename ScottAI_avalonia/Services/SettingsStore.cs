using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// То, что лаунчер помнит между запусками: оформление и профиль пользователя.
/// Всё остальное (голос Scott, провайдер ИИ, макросы) хранит backend — здесь
/// только то, что живёт исключительно в интерфейсе.
/// </summary>
public sealed class LauncherSettings
{
    /// <summary>"classic" | "glass" | "terminal" — те же имена, что в SettingsViewModel.</summary>
    public string Style { get; set; } = "classic";

    /// <summary>Значимо только для Classic: Glass и Terminal всегда тёмные.</summary>
    public bool IsDark { get; set; } = true;

    public string AccentHex { get; set; } = "#3B82F6";

    /// <summary>Непрозрачность фона Glass в процентах, 15-100.</summary>
    public double GlassOpacity { get; set; } = 55;

    public string UserName { get; set; } = "";

    public string Bio { get; set; } = "";

    // ---- Кадрирование аватара ----
    // Фото почти никогда не годится «как есть»: лицо на снимке смещено от
    // центра, и круглая рамка обрезает его как попало. Поэтому запоминается,
    // какую именно часть картинки человек выбрал — сдвиг от центра в долях
    // размера рамки и увеличение.
    public double AvatarOffsetX { get; set; }

    public double AvatarOffsetY { get; set; }

    /// <summary>Увеличение фото в рамке: 1 — вписано целиком, больше — приближено.</summary>
    public double AvatarZoom { get; set; } = 1.0;

    /// <summary>
    /// Продолжать работать после закрытия окна.
    ///
    /// Для голосового ассистента это состояние по умолчанию: смысл в том,
    /// чтобы услышать «Скотт, открой браузер» тогда, когда окно давно закрыто.
    /// Окно при этом прячется в область уведомлений, откуда его можно вернуть
    /// или выйти по-настоящему.
    /// </summary>
    public bool RunInBackground { get; set; } = true;

    /// <summary>
    /// Какая иконка у приложения: "dark" или "light".
    ///
    /// Выбор оставлен человеку, а не привязан к теме лаунчера: тема окна и
    /// тема панели задач у него могут не совпадать, и на светлой панели
    /// тёмная иконка со свечением выглядит чёрным пятном.
    /// </summary>
    public string IconVariant { get; set; } = "dark";
}

[JsonSourceGenerationOptions(WriteIndented = true)]
[JsonSerializable(typeof(LauncherSettings))]
internal partial class SettingsJsonContext : JsonSerializerContext
{
}

/// <summary>
/// Чтение и запись настроек лаунчера.
///
/// Файл лежит в %APPDATA%\ScottAI, а не рядом с проектом, и это осознанно:
/// папка проекта уже дважды переезжала (сначала внутри OneDrive, потом в
/// корень диска), и настройки не должны исчезать вместе с переездом. По той
/// же причине там же хранятся модели Whisper и Silero — в ~/.cache/torch.
///
/// Ни одна ошибка ввода-вывода не должна ронять лаунчер: настройки — вещь
/// приятная, но не критичная, поэтому при любом сбое чтения возвращаются
/// значения по умолчанию, а сбой записи просто игнорируется.
/// </summary>
public static class SettingsStore
{
    private static readonly string Dir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "ScottAI");

    private static readonly string FilePath = Path.Combine(Dir, "launcher.json");

    /// <summary>Аватар лежит отдельным файлом: складывать картинку в JSON строкой base64 —
    /// значит раздувать конфиг до сотен килобайт и терять возможность просто её посмотреть.</summary>
    private static readonly string AvatarPath = Path.Combine(Dir, "avatar.png");

    /// <summary>
    /// Единственный экземпляр настроек на всё приложение. Оформление правится на
    /// странице Настроек, имя и аватар — на странице Профиля; будь у каждой свой
    /// объект, сохранение одной страницы затирало бы изменения другой.
    /// </summary>
    public static LauncherSettings Current { get; } = Load();

    /// <summary>Записать текущие настройки. Вызывается после каждого изменения:
    /// их мало, файл крошечный, и так ничего не теряется при закрытии окна.</summary>
    public static void SaveCurrent() => Save(Current);

    public static LauncherSettings Load()
    {
        try
        {
            if (File.Exists(FilePath))
            {
                var json = File.ReadAllText(FilePath);
                var loaded = JsonSerializer.Deserialize(json, SettingsJsonContext.Default.LauncherSettings);
                if (loaded != null)
                {
                    // Значение из файла могло быть испорчено руками — приводим в
                    // допустимый диапазон, иначе окно станет нечитаемым.
                    loaded.GlassOpacity = Math.Clamp(loaded.GlassOpacity, 15, 100);
                    return loaded;
                }
            }
        }
        catch (Exception)
        {
            // Повреждённый или недоступный файл — не повод падать при запуске.
        }

        return new LauncherSettings();
    }

    public static void Save(LauncherSettings settings)
    {
        try
        {
            Directory.CreateDirectory(Dir);
            var json = JsonSerializer.Serialize(settings, SettingsJsonContext.Default.LauncherSettings);
            File.WriteAllText(FilePath, json);
        }
        catch (Exception)
        {
            // Настройка не сохранилась — пользователь переживёт, падение лаунчера нет.
        }
    }

    public static byte[]? LoadAvatar()
    {
        try
        {
            return File.Exists(AvatarPath) ? File.ReadAllBytes(AvatarPath) : null;
        }
        catch (Exception)
        {
            return null;
        }
    }

    /// <summary>Записать аватар или, если передан null, убрать сохранённый.</summary>
    public static void SaveAvatar(byte[]? bytes)
    {
        try
        {
            if (bytes == null)
            {
                if (File.Exists(AvatarPath)) File.Delete(AvatarPath);
                return;
            }

            Directory.CreateDirectory(Dir);
            File.WriteAllBytes(AvatarPath, bytes);
        }
        catch (Exception)
        {
            // См. Save: сохранение настроек не должно ломать работу.
        }
    }
}
