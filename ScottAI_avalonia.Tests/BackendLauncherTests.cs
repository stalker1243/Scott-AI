using System;
using System.IO;
using System.Linq;
using System.Diagnostics;
using ScottAI.Avalonia.Services;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Поиск Python и запуск backend.
///
/// Здесь было два дефекта, и оба живые.
///
/// Первый: лаунчер искал только системный Python и отвечал «не нашёл Python»
/// на машине, где интерпретатор лежал в соседней папке — его туда кладёт сам
/// установщик. Человек видел отказ и не мог ничего сделать.
///
/// Второй тише: проба перенаправляла оба потока процесса, но не читала их.
/// Труба вмещает четыре килобайта, и наполнив её, кандидат встаёт на записи
/// навсегда. Лаунчер ждал бы по четыре секунды на каждом и объявил, что Python
/// не найден, — хотя тот стоит на месте.
/// </summary>
public class BackendLauncherTests
{
    // ==================== Проба ====================
    //
    // Команды для пробы берутся по системе. Раньше здесь всюду стоял cmd, и на
    // macOS-раннере две проверки легли: такой программы там нет, а проба честно
    // ответила «не запустилось». Проверялось, выходит, не поведение пробы, а то,
    // что её запустили на Windows.

    private static (string File, string Args) Оболочка(string команда) =>
        OperatingSystem.IsWindows()
            ? ("cmd", "/c " + команда)
            : ("/bin/sh", "-c \"" + команда + "\"");

    private static bool Проба(string команда)
    {
        var (file, args) = Оболочка(команда);
        return BackendLauncher.Probe(file, args);
    }

    [Fact]
    public void Проба_видит_успешную_команду()
    {
        Assert.True(Проба("exit 0"), "проба не признала успешно завершившуюся команду");
    }

    [Fact]
    public void Проба_видит_неудачную_команду()
    {
        Assert.False(Проба("exit 1"));
    }

    [Fact]
    public void Несуществующая_программа_не_роняет_пробу()
    {
        // Кандидатов перебирают по очереди, и отсутствие первого — обычное
        // дело, а не повод падать.
        Assert.False(BackendLauncher.Probe("такой-программы-нет-12345", "--version"));
    }

    [Fact]
    public void Многословный_вывод_не_вешает_пробу()
    {
        // Тот самый случай: труба вмещает четыре килобайта. Не вычитывая её,
        // проба ждала бы вечно, а лаунчер объявил бы, что Python не найден.
        //
        // Здесь команда печатает заметно больше четырёх килобайт.
        var строка = new string('x', 60);
        var многословная = OperatingSystem.IsWindows()
            ? $"for /L %i in (1,1,400) do @echo {строка}"
            : $"for i in $(seq 400); do echo {строка}; done";

        var начало = Stopwatch.StartNew();
        var успех = Проба(многословная);
        начало.Stop();

        Assert.True(успех, "проба не дождалась многословной команды");
        Assert.True(начало.Elapsed < TimeSpan.FromSeconds(4),
            $"проба провисела {начало.Elapsed.TotalSeconds:0.0} с — похоже на затор в трубе");
    }

    // ==================== Встроенный Python ====================

    [Fact]
    public void Встроенный_python_находится_рядом_с_программой()
    {
        // Установщик кладёт интерпретатор в папку runtime рядом с лаунчером.
        // Именно этого лаунчер когда-то и не умел находить.
        var корень = Path.Combine(Path.GetTempPath(), "scott-test-" + Guid.NewGuid().ToString("N")[..8]);
        var рядом = Path.Combine(корень, "launcher");
        var runtime = Path.Combine(корень, "runtime");
        Directory.CreateDirectory(рядом);
        Directory.CreateDirectory(runtime);

        var интерпретатор = Path.Combine(runtime, OperatingSystem.IsWindows() ? "python.exe" : "bin/python3");
        Directory.CreateDirectory(Path.GetDirectoryName(интерпретатор)!);
        File.WriteAllText(интерпретатор, "");

        try
        {
            var найден = BackendLauncher.FindBundledPython(рядом);

            Assert.NotNull(найден);
            Assert.Equal(интерпретатор, найден);
        }
        finally
        {
            Directory.Delete(корень, recursive: true);
        }
    }

    [Fact]
    public void Без_встроенного_python_возвращается_пусто()
    {
        // Пара к тесту выше: на машине разработчика runtime рядом нет, и это
        // не ошибка — дальше в очереди стоит системный интерпретатор.
        var пустая = Path.Combine(Path.GetTempPath(), "scott-empty-" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(пустая);

        try
        {
            Assert.Null(BackendLauncher.FindBundledPython(пустая));
        }
        finally
        {
            Directory.Delete(пустая, recursive: true);
        }
    }

    // ==================== Очередь кандидатов ====================

    [Fact]
    public void Системные_кандидаты_перечислены()
    {
        var кандидаты = BackendLauncher.Candidates().ToList();

        Assert.NotEmpty(кандидаты);

        if (OperatingSystem.IsWindows())
        {
            // Версия указывается явно: на машине обычно несколько Python, а
            // backend рассчитан на 3.13. Без указания py возьмёт версию по
            // умолчанию — какую угодно.
            var py = кандидаты.FirstOrDefault(к => к.File == "py");
            Assert.Contains("3.13", py.Prefix);
        }
    }

    [Fact]
    public void Backend_находится_внутри_бандла_macos()
    {
        // На macOS программа — папка со строгим устройством: исполняемый файл
        // в Contents/MacOS, всё остальное в Contents/Resources. Положить
        // backend рядом с исполняемым файлом нельзя — подпись бандла считает
        // посторонние файлы в MacOS/ нарушением, и система откажется
        // запускать программу. Значит искать его надо на уровень выше и вбок.
        var корень = Path.Combine(Path.GetTempPath(), "scott-app-" + Guid.NewGuid().ToString("N")[..8]);
        var macos = Path.Combine(корень, "ScottAI.app", "Contents", "MacOS");
        var backend = Path.Combine(корень, "ScottAI.app", "Contents", "Resources", "backend");

        Directory.CreateDirectory(macos);
        Directory.CreateDirectory(backend);
        File.WriteAllText(Path.Combine(backend, "main.py"), "");

        try
        {
            // Признак системы задаётся явно: иначе эту ветку нельзя проверить
            // ниоткуда, кроме самого Mac, а пишется она как раз не на нём.
            Assert.Equal(backend, BackendLauncher.FindBackendDirectory(macos, macOS: true));
        }
        finally
        {
            Directory.Delete(корень, recursive: true);
        }
    }

    [Fact]
    public void Backend_рядом_с_программой_находится_везде()
    {
        // Обычный случай Windows и Linux, и он должен продолжать работать: в
        // поиск добавилось место, а не заменилось.
        var корень = Path.Combine(Path.GetTempPath(), "scott-plain-" + Guid.NewGuid().ToString("N")[..8]);
        var программа = Path.Combine(корень, "launcher");
        var backend = Path.Combine(корень, "backend");

        Directory.CreateDirectory(программа);
        Directory.CreateDirectory(backend);
        File.WriteAllText(Path.Combine(backend, "main.py"), "");

        try
        {
            Assert.Equal(backend, BackendLauncher.FindBackendDirectory(программа, macOS: false));
        }
        finally
        {
            Directory.Delete(корень, recursive: true);
        }
    }

    [Fact]
    public void Вне_macos_в_resources_не_заглядываем()
    {
        // Лишнее место поиска — не безобидная мелочь: папка Resources есть и в
        // других программах, и найденный там чужой main.py лаунчер честно
        // попытался бы запустить.
        var уровни = BackendLauncher.BackendCandidates("/тут", macOS: false);

        Assert.Single(уровни);
    }
}
