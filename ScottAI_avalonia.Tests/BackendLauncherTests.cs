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

    [Fact]
    public void Проба_видит_успешную_команду()
    {
        var успех = BackendLauncher.Probe("cmd", "/c exit 0");
        Assert.True(успех, "проба не признала успешно завершившуюся команду");
    }

    [Fact]
    public void Проба_видит_неудачную_команду()
    {
        Assert.False(BackendLauncher.Probe("cmd", "/c exit 1"));
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
        var начало = Stopwatch.StartNew();
        var успех = BackendLauncher.Probe("cmd", "/c for /L %i in (1,1,400) do @echo " + new string('x', 60));
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
}
