using System;
using System.Globalization;
using Avalonia.Media;
using ScottAI.Avalonia.Converters;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Нагрузка машины в то, что видно на голограмме.
///
/// Голограмма на главной странице показывает четыре подсистемы: голова —
/// видеокарта, ядро в груди — процессор, корпус — память, основание — диск.
/// Смысл несут цвет и высота заливки, а не подписи: человек должен понять
/// состояние машины одним взглядом, не читая цифр.
///
/// Значит, ошибка здесь не косметическая. Перевёрнутая шкала показала бы
/// спокойный цвет на перегруженной машине, а перевёрнутая заливка — полный бак
/// при пустом. Второе, кстати, и случилось: часть тела дважды наливалась сверху
/// вниз, пока заливку не переложили на градиент по силуэту.
/// </summary>
public class LoadConverterTests
{
    private static readonly CultureInfo Культура = CultureInfo.InvariantCulture;

    // ==================== Цвет ====================

    [Fact]
    public void Спокойная_машина_светится_бирюзовым()
    {
        var цвет = LoadToBrushConverter.ColorFor(0);

        Assert.Equal(LoadToBrushConverter.Calm, цвет);
    }

    [Fact]
    public void Загруженная_машина_краснеет()
    {
        var цвет = LoadToBrushConverter.ColorFor(100);

        Assert.Equal(LoadToBrushConverter.Hot, цвет);
    }

    [Theory]
    [InlineData(0, 30)]
    [InlineData(30, 60)]
    [InlineData(60, 85)]
    [InlineData(85, 100)]
    public void Цвет_теплеет_с_ростом_нагрузки(double меньше, double больше)
    {
        // Не проверка конкретных оттенков — проверка направления. Переход
        // должен быть однонаправленным на всём отрезке, иначе шкала перестаёт
        // читаться: на шестидесяти процентах цвет не может быть спокойнее, чем
        // на тридцати.
        var холодный = LoadToBrushConverter.ColorFor(меньше);
        var тёплый = LoadToBrushConverter.ColorFor(больше);

        Assert.True(Теплота(тёплый) > Теплота(холодный),
            $"{меньше}% выглядит горячее, чем {больше}%");
    }

    /// <summary>
    /// Насколько цвет тревожен: красного больше, зелёного меньше.
    ///
    /// Мерка выбрана не сразу. Сначала было «красный минус синий», и проверка
    /// на этом же и споткнулась: у янтарного синего почти нет, поэтому по такой
    /// мерке он выходит «теплее» чистого красного. А путь от янтарного к
    /// красному — это именно уход зелёного.
    /// </summary>
    private static int Теплота(Color цвет) => цвет.R - цвет.G;

    [Fact]
    public void Переход_плавный_без_ступеней()
    {
        // Резкие ступени превратили бы шкалу в три состояния вместо
        // непрерывной величины, и разница между 51% и 74% пропала бы.
        var шаги = 0;
        var предыдущий = LoadToBrushConverter.ColorFor(0);

        for (var процент = 1; процент <= 100; процент++)
        {
            var текущий = LoadToBrushConverter.ColorFor(процент);
            var скачок = Math.Abs(текущий.R - предыдущий.R)
                       + Math.Abs(текущий.G - предыдущий.G)
                       + Math.Abs(текущий.B - предыдущий.B);

            if (скачок > 20) шаги++;
            предыдущий = текущий;
        }

        Assert.Equal(0, шаги);
    }

    [Theory]
    [InlineData(-50)]
    [InlineData(500)]
    [InlineData(double.NaN)]
    public void Невозможные_значения_не_ломают_цвет(double процент)
    {
        // Метрики приходят из сети и могут оказаться любыми — особенно когда
        // backend только поднимается.
        var исключение = Record.Exception(() => LoadToBrushConverter.ColorFor(процент));

        Assert.Null(исключение);
    }

    // ==================== Граница заливки ====================

    [Theory]
    [InlineData(0, 1.0)]
    [InlineData(50, 0.5)]
    [InlineData(100, 0.0)]
    public void Граница_заливки_поднимается_с_нагрузкой(double процент, double ожидается)
    {
        // У градиента ноль наверху, единица внизу — поэтому чем больше
        // нагрузка, тем меньше число. Ровно на этом развороте координат и
        // ошибались: часть тела дважды наливалась сверху вниз.
        var граница = (double)LoadToFillEdgeConverter.Instance.Convert(
            процент, typeof(double), null, Культура);

        Assert.Equal(ожидается, граница, precision: 3);
    }

    [Fact]
    public void Полная_загрузка_заливает_часть_целиком()
    {
        var граница = (double)LoadToFillEdgeConverter.Instance.Convert(
            100, typeof(double), null, Культура);

        Assert.Equal(0.0, граница, precision: 3);
    }

    [Fact]
    public void Мягкая_кромка_выше_самой_границы()
    {
        // Вторая точка градиента стоит выше первой: без этого граница выглядит
        // срезом ножницами, а не поверхностью налитой жидкости.
        var граница = (double)LoadToFillEdgeConverter.Instance.Convert(
            50, typeof(double), null, Культура);
        var кромка = (double)LoadToFillEdgeConverter.Instance.Convert(
            50, typeof(double), "feather", Культура);

        Assert.True(кромка < граница, "кромка не выше границы — заливка обрежется ножницами");
    }

    [Theory]
    [InlineData(0)]
    [InlineData(100)]
    public void Граница_не_выходит_за_пределы_градиента(double процент)
    {
        // Точка градиента за отрезком [0, 1] — это исключение при отрисовке,
        // то есть пустое место вместо фигуры.
        foreach (var параметр in new string?[] { null, "feather" })
        {
            var значение = (double)LoadToFillEdgeConverter.Instance.Convert(
                процент, typeof(double), параметр, Культура);

            Assert.InRange(значение, 0.0, 1.0);
        }
    }

    // ==================== Свечение и высота ====================

    [Fact]
    public void Простаивающая_часть_всё_равно_светится()
    {
        // Погасшая часть не отличалась бы от «данных нет»: человек решил бы,
        // что видеокарты в машине нет вовсе.
        var свечение = (double)LoadToGlowConverter.Instance.Convert(0, typeof(double), null, Культура);

        Assert.True(свечение > 0.2, "простаивающая часть погасла совсем");
        Assert.True(свечение < 1.0, "простаивающая часть светится как загруженная");
    }

    [Fact]
    public void Свечение_растёт_с_нагрузкой()
    {
        var тихо = (double)LoadToGlowConverter.Instance.Convert(10, typeof(double), null, Культура);
        var громко = (double)LoadToGlowConverter.Instance.Convert(90, typeof(double), null, Культура);

        Assert.True(громко > тихо);
    }

    [Theory]
    [InlineData(0, LoadToHeightConverter.MinVisible)]
    [InlineData(50, 50.0)]
    [InlineData(100, 100.0)]
    public void Высота_заполнения_пропорциональна_нагрузке(double процент, double ожидается)
    {
        var высота = (double)LoadToHeightConverter.Instance.Convert(
            процент, typeof(double), "100", Культура);

        Assert.Equal(ожидается, высота, precision: 3);
    }

    [Fact]
    public void Пустая_полоса_всё_равно_видна()
    {
        // Полоса нулевой длины исчезает совсем, и человек не отличает «диск
        // пуст» от «данных нет».
        var высота = (double)LoadToHeightConverter.Instance.Convert(
            0, typeof(double), "100", Культура);

        Assert.True(высота >= LoadToHeightConverter.MinVisible);
    }

    // ==================== Цвет для точки градиента ====================

    [Fact]
    public void Цвет_точки_совпадает_с_цветом_кисти()
    {
        // Два преобразователя дают одно и то же разными типами: точке градиента
        // нужен Color, а обводке — кисть. Разойдись они, контур части светился
        // бы одним цветом, а заливка другим.
        foreach (var процент in new double[] { 0, 25, 50, 75, 100 })
        {
            var цветТочки = (Color)LoadToColorConverter.Instance.Convert(
                процент, typeof(Color), null, Культура);
            var кисть = (SolidColorBrush)LoadToBrushConverter.Instance.Convert(
                процент, typeof(IBrush), null, Культура);

            Assert.Equal(кисть.Color, цветТочки);
        }
    }
}
