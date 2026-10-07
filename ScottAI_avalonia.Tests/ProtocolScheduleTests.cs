using System.Text.Json;
using ScottAI.Avalonia.Models;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Расписание протокола в списке лаунчера.
///
/// Проверяется стык с backend: тот отдаёт расписание словами в поле
/// «schedule_text», и переименование этого поля с одной стороны не сломает ни
/// сборку, ни один запрос — протокол просто начнёт выглядеть так, будто
/// расписания у него нет. Человек при этом будет уверен, что Scott разбудит его
/// в девять.
/// </summary>
[Collection("avalonia")]
public class ProtocolScheduleTests
{
    private static Protocol Разобрать(string json) =>
        JsonSerializer.Deserialize<Protocol>(json)!;

    [Fact]
    public void Расписание_из_ответа_backend_видно_в_строке()
    {
        var протокол = Разобрать("""
            {"name":"Работа","steps":[{"text":"открой браузер"}],
             "schedule_text":"по будням в 09:00"}
            """);

        Assert.True(протокол.HasSchedule);
        Assert.Contains("по будням в 09:00", протокол.ScheduleLine);
    }

    [Fact]
    public void Без_расписания_протокол_ждёт_когда_позовут()
    {
        var протокол = Разобрать("""
            {"name":"Работа","steps":[{"text":"открой браузер"}]}
            """);

        Assert.False(протокол.HasSchedule);
        Assert.Equal("запускается по просьбе", протокол.ScheduleLine);
    }
}
