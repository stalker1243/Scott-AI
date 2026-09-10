using System;
using System.IO;
using ScottAI.Avalonia.Services;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Хранение настроек лаунчера.
///
/// Настройки лежат в %APPDATA% и намеренно переживают переустановку — иначе
/// каждое обновление сбрасывало бы вид программы. Обратная сторона тоже живая:
/// поставив Scott заново, человек увидел свой прежний профиль и решил, что
/// установка прошла не начисто. Отсюда явный способ начать с чистого листа.
///
/// Файл при этом читается на каждом запуске и может оказаться каким угодно:
/// его правили руками, он остался от прежней версии, диск был занят на записи.
/// Ни один из этих случаев не должен мешать программе открыться.
///
/// Проверки работают в своей временной папке, а не в настоящей: иначе они
/// портили бы настройки человека, который их запускает.
/// </summary>
public class SettingsStoreTests : IDisposable
{
    private readonly string _папка;

    public SettingsStoreTests()
    {
        _папка = Path.Combine(Path.GetTempPath(), "scott-settings-" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(_папка);
    }

    public void Dispose()
    {
        try { Directory.Delete(_папка, recursive: true); } catch { }
    }

    private string ФайлНастроек => Path.Combine(_папка, SettingsStore.FileName);

    // ==================== Туда и обратно ====================

    [Fact]
    public void Настройки_переживают_запись_и_чтение()
    {
        var настройки = new LauncherSettings
        {
            Style = "glass",
            IsDark = false,
            AccentHex = "#22C55E",
            GlassOpacity = 42,
            UserName = "Фантом",
            Bio = "разработчик",
            RunInBackground = true,
            IconVariant = "light",
        };

        SettingsStore.SaveTo(настройки, _папка);
        var прочитанные = SettingsStore.LoadFrom(_папка);

        Assert.Equal("glass", прочитанные.Style);
        Assert.False(прочитанные.IsDark);
        Assert.Equal("#22C55E", прочитанные.AccentHex);
        Assert.Equal(42, прочитанные.GlassOpacity);
        Assert.Equal("Фантом", прочитанные.UserName);
        Assert.Equal("разработчик", прочитанные.Bio);
        Assert.True(прочитанные.RunInBackground);
        Assert.Equal("light", прочитанные.IconVariant);
    }

    [Fact]
    public void Без_файла_берутся_значения_по_умолчанию()
    {
        // Первый запуск на новой машине — обычное дело, а не ошибка.
        var настройки = SettingsStore.LoadFrom(_папка);

        Assert.Equal("classic", настройки.Style);
        Assert.True(настройки.IsDark);
    }

    // ==================== Испорченный файл ====================

    [Theory]
    [InlineData("{ это не json")]
    [InlineData("")]
    [InlineData("null")]
    [InlineData("[1, 2, 3]")]
    public void Испорченный_файл_не_мешает_запуску(string содержимое)
    {
        // Файл правили руками, он остался от прежней версии, запись оборвалась
        // на середине — во всех случаях программа обязана открыться.
        File.WriteAllText(ФайлНастроек, содержимое);

        var настройки = SettingsStore.LoadFrom(_папка);

        Assert.NotNull(настройки);
        Assert.Equal("classic", настройки.Style);
    }

    [Fact]
    public void Прозрачность_приводится_в_допустимый_диапазон()
    {
        // Значение можно поправить руками, а окно с прозрачностью в один
        // процент становится нечитаемым, и вернуть настройку человеку уже
        // нечем — он не видит, куда нажимать.
        File.WriteAllText(ФайлНастроек, "{\"GlassOpacity\": 1}");
        Assert.InRange(SettingsStore.LoadFrom(_папка).GlassOpacity, 15, 100);

        File.WriteAllText(ФайлНастроек, "{\"GlassOpacity\": 900}");
        Assert.InRange(SettingsStore.LoadFrom(_папка).GlassOpacity, 15, 100);
    }

    [Fact]
    public void Недоступная_папка_не_роняет_сохранение()
    {
        // Диск занят, папка удалена, прав нет — настройка не сохранится, и это
        // переживаемо. Падение лаунчера в этот момент — нет.
        var несуществующая = Path.Combine(_папка, "нет", "\0такой", "папки");

        var исключение = Record.Exception(
            () => SettingsStore.SaveTo(new LauncherSettings(), несуществующая));

        Assert.Null(исключение);
    }

    // ==================== Сброс ====================

    [Fact]
    public void Сброс_возвращает_все_поля_к_исходным()
    {
        // Самая вероятная ошибка здесь молчаливая: добавили поле в настройки и
        // забыли добавить в сброс — «сбросить настройки» оставляет его
        // прежним, а человек уверен, что начал с чистого листа.
        var настройки = new LauncherSettings
        {
            Style = "terminal",
            IsDark = false,
            AccentHex = "#EF4444",
            GlassOpacity = 20,
            UserName = "Фантом",
            Bio = "что-то о себе",
            AvatarOffsetX = 15,
            AvatarOffsetY = -8,
            AvatarZoom = 2.5,
            RunInBackground = true,
            IconVariant = "light",
        };

        SettingsStore.ResetFields(настройки);

        var чистые = new LauncherSettings();

        Assert.Equal(чистые.Style, настройки.Style);
        Assert.Equal(чистые.IsDark, настройки.IsDark);
        Assert.Equal(чистые.AccentHex, настройки.AccentHex);
        Assert.Equal(чистые.GlassOpacity, настройки.GlassOpacity);
        Assert.Equal(чистые.UserName, настройки.UserName);
        Assert.Equal(чистые.Bio, настройки.Bio);
        Assert.Equal(чистые.AvatarOffsetX, настройки.AvatarOffsetX);
        Assert.Equal(чистые.AvatarOffsetY, настройки.AvatarOffsetY);
        Assert.Equal(чистые.AvatarZoom, настройки.AvatarZoom);
        Assert.Equal(чистые.RunInBackground, настройки.RunInBackground);
        Assert.Equal(чистые.IconVariant, настройки.IconVariant);
    }

    [Fact]
    public void Сброс_меняет_тот_же_объект_а_не_подменяет_ссылку()
    {
        // Страницы Настроек и Профиля держат именно этот объект. Новая копия
        // до них бы не дошла, и человек не увидел бы сброса до перезапуска.
        var настройки = new LauncherSettings { UserName = "Фантом" };
        var прежняя_ссылка = настройки;

        SettingsStore.ResetFields(настройки);

        Assert.Same(прежняя_ссылка, настройки);
        Assert.Equal("", настройки.UserName);
    }
}
