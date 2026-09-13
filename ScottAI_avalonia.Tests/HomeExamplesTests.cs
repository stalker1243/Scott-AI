using System.Linq;
using ScottAI.Avalonia.ViewModels;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Подсказки на главной странице.
///
/// Четыре примера стояли намертво, и после третьего открытия лаунчера человек
/// переставал их замечать. Это единственное место, где видно, что Scott вообще
/// умеет, — и список из четырёх строк создавал впечатление, что умеет он ровно
/// четыре вещи.
/// </summary>
public class HomeExamplesTests
{
    [Fact]
    public void Показываются_четыре_подсказки()
    {
        Assert.Equal(4, HomeExamples.PickFour().Length);
    }

    [Fact]
    public void Подсказки_меняются_от_запуска_к_запуску()
    {
        // Смысл всей затеи. Случай может дважды выдать одно и то же, поэтому
        // проверяется не пара наборов, а два десятка: если выбор не работает
        // вовсе, все они окажутся одинаковыми.
        var наборы = Enumerable.Range(0, 20)
            .Select(_ => string.Join("|", HomeExamples.PickFour().Select(e => e.Text)))
            .Distinct()
            .Count();

        Assert.True(наборы > 1, "подсказки не меняются между запусками");
    }

    [Fact]
    public void В_каждом_наборе_есть_дело_а_не_только_вопросы()
    {
        // Простой случайный выбор из общего мешка регулярно выдавал четыре
        // вопроса подряд, и выходило, что Scott умеет только отвечать. Поэтому
        // берётся по одному примеру из каждого вида дел.
        //
        // Проверяется через запуски: в каждом наборе обязан быть пример,
        // который что-то делает, а не спрашивает.
        for (var i = 0; i < 30; i++)
        {
            var набор = HomeExamples.PickFour();

            Assert.Contains(набор, e =>
                e.Text.StartsWith("Открой") ||
                e.Text.StartsWith("Закрой") ||
                e.Text.StartsWith("Заверши"));
        }
    }

    [Fact]
    public void У_каждой_подсказки_есть_текст_и_значок()
    {
        // Подсказка без значка выглядит на странице поломкой: у соседних он
        // есть, и пустое место читается как не загрузившаяся картинка.
        for (var i = 0; i < 30; i++)
        {
            foreach (var пример in HomeExamples.PickFour())
            {
                Assert.False(string.IsNullOrWhiteSpace(пример.Text));
                Assert.False(string.IsNullOrWhiteSpace(пример.Icon));
            }
        }
    }

    [Fact]
    public void Подсказки_в_наборе_не_повторяются()
    {
        for (var i = 0; i < 30; i++)
        {
            var тексты = HomeExamples.PickFour().Select(e => e.Text).ToList();
            Assert.Equal(тексты.Count, тексты.Distinct().Count());
        }
    }
}
