using System;
using System.Globalization;
using Material.Icons;
using ScottAI.Avalonia.Converters;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Преобразователи значений: то, что превращает состояние в то, что видно.
///
/// По отдельности каждый прост, но их дюжина, и через них проходит почти всё
/// содержимое окна: подсветка активной страницы, сторона, с которой рисуется
/// пузырь в чате, цвет точки состояния, значок молчания. Ошибка здесь не роняет
/// программу — она молча рисует не то, и заметить это можно только глазами.
///
/// Ровно так и вышло с молчанием: значок был правильный, а подпись говорила
/// «Тихий режим» на кнопке, которая означала совсем другое.
/// </summary>
public class ConverterTests
{
    private static readonly CultureInfo Культура = CultureInfo.InvariantCulture;

    // ==================== Сравнение с образцом ====================

    [Theory]
    [InlineData("home", "home", true)]
    [InlineData("home", "chat", false)]
    [InlineData(null, "home", false)]
    [InlineData("home", null, false)]
    public void Сравнение_подсвечивает_нужную_страницу(string? значение, string? образец, bool ожидается)
    {
        // По этому преобразователю подсвечивается активная кнопка сайдбара и
        // выбранная вкладка настроек. Ошибка означает, что человек не видит,
        // где находится.
        var итог = EqualsConverter.Instance.Convert(значение, typeof(bool), образец, Культура);

        Assert.Equal(ожидается, итог);
    }

    // ==================== Пустой список ====================

    [Theory]
    [InlineData(0, true)]
    [InlineData(1, false)]
    [InlineData(42, false)]
    public void Ноль_показывает_подсказку_вместо_пустоты(int сколько, bool ожидается)
    {
        // На пустом списке вместо голого места показывается объяснение, почему
        // он пуст. Это единственное, что человек увидит, открыв раздел впервые.
        var итог = IsZeroConverter.Instance.Convert(сколько, typeof(bool), null, Культура);

        Assert.Equal(ожидается, итог);
    }

    [Fact]
    public void Не_число_пустотой_не_считается()
    {
        // Значение приходит из привязки и может оказаться чем угодно, включая
        // null во время загрузки. Подсказка «пусто» на непонятном значении
        // вводила бы в заблуждение.
        Assert.Equal(false, IsZeroConverter.Instance.Convert(null, typeof(bool), null, Культура));
        Assert.Equal(false, IsZeroConverter.Instance.Convert("0", typeof(bool), null, Культура));
    }

    // ==================== Молчание ====================

    [Fact]
    public void Значок_молчания_перечёркнут()
    {
        Assert.Equal(MaterialIconKind.VolumeOff,
            QuietIconConverter.Instance.Convert(true, typeof(MaterialIconKind), null, Культура));

        Assert.Equal(MaterialIconKind.VolumeHigh,
            QuietIconConverter.Instance.Convert(false, typeof(MaterialIconKind), null, Культура));
    }

    [Fact]
    public void Подсказка_молчания_говорит_о_действии_а_не_о_состоянии()
    {
        // Человек наводит курсор, чтобы узнать, что случится при нажатии.
        // «Тихий режим включён» на это не отвечает.
        var молчит = (string)QuietTipConverter.Instance.Convert(true, typeof(string), null, Культура);
        var говорит = (string)QuietTipConverter.Instance.Convert(false, typeof(string), null, Культура);

        Assert.Contains("вернуть голос", молчит);
        Assert.Contains("помолчать", говорит);
        Assert.NotEqual(молчит, говорит);
    }

    [Fact]
    public void Подписи_чата_и_общего_молчания_не_совпадают()
    {
        // Здесь уже был дефект: кнопка в чате называлась «Тихий режим» — так
        // же, как общая настройка, — но означала другое. Человек выключал звук
        // в шапке и видел в чате бодрое «Озвучка: вкл».
        var чат = (string)ChatVoiceLabelConverter.Instance.Convert(true, typeof(string), null, Культура);
        var общее = (string)QuietTipConverter.Instance.Convert(true, typeof(string), null, Культура);

        Assert.NotEqual(чат, общее);
        Assert.DoesNotContain("Тихий режим", чат);
    }

    // ==================== Доли в пиксели ====================

    [Theory]
    [InlineData(0.5, "200", 100.0)]
    [InlineData(1.0, "200", 200.0)]
    [InlineData(0.25, "80", 20.0)]
    public void Доля_превращается_в_ширину(double доля, string предел, double ожидается)
    {
        var итог = FractionToPixelsConverter.Instance.Convert(доля, typeof(double), предел, Культура);

        Assert.Equal(ожидается, Assert.IsType<double>(итог), precision: 3);
    }

    [Fact]
    public void Нулевой_столбик_всё_равно_виден()
    {
        // Два пикселя вместо нуля — намеренно. Столбик нулевой высоты исчезает
        // с графика совсем, и человек не отличает «значение ноль» от «данных
        // нет вовсе».
        var итог = (double)FractionToPixelsConverter.Instance.Convert(0.0, typeof(double), "200", Культура);

        Assert.Equal(2.0, итог, precision: 3);
    }

    [Fact]
    public void Испорченный_предел_не_роняет_разметку()
    {
        // Параметр приходит строкой прямо из разметки, и опечатка в ней не
        // должна ломать страницу — там просто возьмётся значение по умолчанию.
        var итог = FractionToPixelsConverter.Instance.Convert(0.5, typeof(double), "не число", Культура);

        Assert.IsType<double>(итог);
    }

    // ==================== Обратное преобразование ====================

    [Fact]
    public void Обратное_преобразование_честно_отказывается()
    {
        // Молчаливое возвращение null здесь опаснее исключения: привязка
        // продолжила бы работать и записала бы в состояние пустоту.
        Assert.Throws<NotSupportedException>(() =>
            EqualsConverter.Instance.ConvertBack(true, typeof(string), null, Культура));

        Assert.Throws<NotSupportedException>(() =>
            QuietIconConverter.Instance.ConvertBack(true, typeof(bool), null, Культура));
    }
}
