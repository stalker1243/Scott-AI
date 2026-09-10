using System.Reflection;
using ScottAI.Avalonia.Services;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Иконки должны находиться по своим адресам.
///
/// Здесь уже был дефект, и самый дорогой из всех: программу переименовали
/// (ScottAI.Avalonia → ScottAI), адреса ресурсов вида avares://ScottAI.Avalonia/
/// перестали существовать, и версия 1.0.5 не запускалась вовсе. Молча — падение
/// происходило до появления окна, так что человек нажимал на ярлык и не видел
/// ничего. Нашлось это только тем, что пользователь пожаловался.
///
/// Проверка занимает миллисекунды и ловит ровно этот случай. Важно, что она
/// зовёт те же самые методы, что и программа: считать адрес самостоятельно
/// значило бы проверять собственную арифметику, а не работу службы. Первая
/// попытка так и вышла — с заведомо сломанным именем сборки четыре проверки из
/// пяти остались зелёными.
/// </summary>
[Collection("avalonia")]
public class AppIconTests
{
    [Theory]
    [InlineData(AppIconService.Dark)]
    [InlineData(AppIconService.Light)]
    public void Логотип_загружается(string вариант)
    {
        var логотип = AppIconService.LoadLogo(вариант);

        Assert.True(логотип is not null,
            $"Логотип варианта «{вариант}» не загрузился — в сайдбаре будет пусто");
    }

    [Theory]
    [InlineData(AppIconService.Dark)]
    [InlineData(AppIconService.Light)]
    public void Иконка_окна_загружается(string вариант)
    {
        var иконка = AppIconService.LoadWindowIcon(вариант);

        Assert.True(иконка is not null,
            $"Иконка варианта «{вариант}» не загрузилась — программа падает до появления окна");
    }

    [Fact]
    public void Адрес_ресурсов_совпадает_с_именем_сборки()
    {
        // Имя берётся на месте, а не пишется строкой. Ровно из-за строки
        // переименование и осталось незамеченным до выпуска.
        var поле = typeof(AppIconService)
            .GetField("Root", BindingFlags.NonPublic | BindingFlags.Static);

        Assert.NotNull(поле);

        var корень = (string)поле!.GetValue(null)!;
        var имя = typeof(AppIconService).Assembly.GetName().Name;

        Assert.Equal($"avares://{имя}/Assets", корень);
    }

    [Theory]
    [InlineData("dark", true)]
    [InlineData("light", true)]
    [InlineData("neon", false)]
    [InlineData("", false)]
    [InlineData(null, false)]
    public void Известны_только_настоящие_варианты(string? вариант, bool ожидается)
    {
        // Настройка приходит из файла, который человек мог править руками или
        // который остался от прежней версии. Неизвестное значение не должно
        // ронять запуск.
        Assert.Equal(ожидается, AppIconService.IsKnown(вариант));
    }
}
