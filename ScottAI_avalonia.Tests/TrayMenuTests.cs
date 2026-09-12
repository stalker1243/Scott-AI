using System.Linq;
using ScottAI.Avalonia.Services;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Меню значка в трее.
///
/// Фоновый режим — обычное состояние Scott: окно закрыто, а он продолжает
/// слушать комнату и отвечать голосом. Из трея при этом не видно ничего, и
/// меню оказывается единственным местом, где можно и узнать состояние, и
/// поменять его, не разворачивая окно.
///
/// Само меню собирается из настоящих элементов Avalonia и требует запущенного
/// приложения, поэтому здесь проверяются две вещи, которые от него не зависят:
/// подписи и устойчивость к системе, где значка нет вовсе.
/// </summary>
public class TrayMenuTests
{
    [Fact]
    public void Подпись_значка_называет_состояние()
    {
        // Подпись — то, что человек видит, наведя курсор, не открывая меню.
        // Все четыре сочетания должны читаться по-разному, иначе она не
        // сообщает ничего.
        var подписи = new[]
        {
            TrayMenuService.Tooltip(quiet: false, listening: false),
            TrayMenuService.Tooltip(quiet: false, listening: true),
            TrayMenuService.Tooltip(quiet: true, listening: false),
            TrayMenuService.Tooltip(quiet: true, listening: true),
        };

        Assert.Equal(подписи.Length, подписи.Distinct().Count());
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public void Подпись_всегда_называет_программу(bool quiet, bool listening)
    {
        // В трее значков много, и подпись — единственное, что отличает один от
        // другого. Название программы в ней быть обязано.
        Assert.Contains("Scott", TrayMenuService.Tooltip(quiet, listening));
    }

    [Fact]
    public void Тихий_режим_виден_в_подписи()
    {
        Assert.Contains("тих", TrayMenuService.Tooltip(quiet: true, listening: false).ToLower());
        Assert.DoesNotContain("тих", TrayMenuService.Tooltip(quiet: false, listening: true).ToLower());
    }

    [Fact]
    public void Слушает_ли_Scott_видно_в_подписи()
    {
        Assert.Contains("слуша", TrayMenuService.Tooltip(quiet: false, listening: true).ToLower());
        Assert.DoesNotContain("слуша", TrayMenuService.Tooltip(quiet: false, listening: false).ToLower());
    }

    [Fact]
    public void Без_значка_в_системе_ничего_не_ломается()
    {
        // Трей есть не везде: на части систем Avalonia его не даёт вовсе, и
        // лаунчер из-за этого падать не должен. На соседнем сервисе, который
        // ставит иконку приложения, этим уже обжигались.
        TrayMenuService.Attach(null, null!);
    }
}

