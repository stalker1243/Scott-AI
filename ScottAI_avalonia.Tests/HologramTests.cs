using System;
using System.Linq;
using Avalonia;
using Avalonia.Media;
using ScottAI.Avalonia.Hologram;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Фигура на главной странице: силуэт и цвет.
///
/// Здесь была объёмная фигура со своим программным отрисовщиком, и проверки
/// ловили в нём настоящие ошибки — перепутанные перёд и зад, свет снизу,
/// фигуру, уезжавшую из кадра при наклоне, кисть, висевшую в стороне от
/// предплечья. Фигура стала плоской, отрисовщик исчез целиком, и проверять
/// теперь надо другое: пропорции силуэта и то, что цвет по-прежнему означает
/// нагрузку.
///
/// Пропорции — не придирка. Именно на них дважды ломалась объёмная фигура: с
/// головой в шестую часть роста и ногами короче трёх голов она читалась куклой,
/// сколько ни улучшай всё остальное.
///
/// Ключевые ширины силуэта — плечи, талия, бёдра — вынесены в именованные
/// величины, и проверка смотрит на них. Первая попытка мерила сам контур,
/// пересекая его с узкой полосой, но пересечение фигур Avalonia считает через
/// графическую подсистему, которой в проверках нет: результат молча выходил
/// пустым.
/// </summary>
[Collection("avalonia")]
public class HologramTests
{
    // ==================== Пропорции ====================

    [Fact]
    public void Фигура_укладывается_в_свои_границы()
    {
        // Силуэт описан в собственной сетке ростом в двести единиц, и
        // отрисовка масштабирует именно её. Часть, вылезшая за объявленные
        // границы, окажется обрезанной на любом размере окна.
        foreach (var (part, shape) in Silhouette.Parts())
        {
            var b = shape.Bounds;

            Assert.True(b.Top >= -0.5, $"{part}: верх на {b.Top:F1}");
            Assert.True(b.Bottom <= Silhouette.Height + 0.5, $"{part}: низ на {b.Bottom:F1}");

            Assert.True(Math.Abs(b.Left) <= Silhouette.HalfWidth + 0.5,
                        $"{part}: левый край на {b.Left:F1}");
            Assert.True(Math.Abs(b.Right) <= Silhouette.HalfWidth + 0.5,
                        $"{part}: правый край на {b.Right:F1}");
        }
    }

    [Fact]
    public void Голова_около_одной_восьмой_роста()
    {
        // Канон восьми голов. С головой в шестую часть роста фигура читается
        // куклой — это уже проверено на объёмной версии.
        var head = Silhouette.Parts().First(p => p.Part == BodyPart.Head).Shape;

        Assert.True(head.Bounds.Top < 4, "макушка должна быть у верхнего края");

        // Череп по ширине близок к своей высоте: голова человека почти
        // круглая в фас, но чуть уже, чем высока.
        var ширина = Silhouette.SkullHalf * 2;
        var высота = 26.0;

        Assert.InRange(Silhouette.Height / высота, 7.0, 8.6);
        Assert.InRange(ширина / высота, 0.7, 1.0);
    }

    [Fact]
    public void Ноги_занимают_половину_роста()
    {
        // Середина роста у человека приходится на пах. Пока ноги были короче
        // трёх голов, фигура выглядела приземистой.
        var legs = Silhouette.Parts().First(p => p.Part == BodyPart.Legs).Shape.Bounds;

        Assert.True(legs.Height / Silhouette.Height > 0.45,
                    $"ноги занимают {legs.Height / Silhouette.Height:P0} роста");

        Assert.True(legs.Bottom > Silhouette.Height - 6, "фигура должна стоять на полу");
    }

    [Fact]
    public void Плечи_шире_талии_и_бёдер()
    {
        // Три перегиба, без которых силуэт перестаёт быть человеческим. Без
        // них получается мешок, и это первое, что выдаёт нарисованную наспех
        // фигуру.
        Assert.True(Silhouette.ShoulderHalf > Silhouette.WaistHalf,
                    $"плечи {Silhouette.ShoulderHalf}, талия {Silhouette.WaistHalf}");

        Assert.True(Silhouette.HipHalf > Silhouette.WaistHalf,
                    $"бёдра {Silhouette.HipHalf}, талия {Silhouette.WaistHalf}");

        Assert.True(Silhouette.ShoulderHalf > Silhouette.HipHalf,
                    $"плечи {Silhouette.ShoulderHalf}, бёдра {Silhouette.HipHalf}");

        // И всё это должно помещаться в объявленную ширину фигуры.
        Assert.True(Silhouette.ShoulderHalf <= Silhouette.HalfWidth);
    }

    [Fact]
    public void Руки_достают_до_середины_бедра()
    {
        // У человека опущенная кисть приходится на середину бедра. Рука,
        // кончающаяся у пояса, выглядит куцей — на объёмной фигуре так и было.
        var arm = Silhouette.Parts().First(p => p.Part == BodyPart.Arms).Shape.Bounds;

        Assert.InRange(arm.Bottom, 112, 138);
        Assert.True(arm.Top < 46, "рука должна начинаться у плеча");
    }

    [Fact]
    public void Свечение_приходится_на_грудь()
    {
        var torso = Silhouette.Parts().First(p => p.Part == BodyPart.Torso).Shape.Bounds;

        Assert.True(Silhouette.Core.Y > torso.Top, "свечение выше корпуса");
        Assert.True(Silhouette.Core.Y < torso.Top + torso.Height / 2,
                    "свечение должно быть на груди, а не на животе");

        Assert.Equal(0, Silhouette.Core.X);
    }

    [Fact]
    public void Выноска_упирается_в_свою_часть()
    {
        // Линия, упирающаяся в пустоту рядом с фигурой, заставляет гадать, о
        // чём речь. Точка привязки обязана лежать в пределах своей части.
        foreach (var (part, shape) in Silhouette.Parts())
        {
            var anchor = Silhouette.Anchor(part);
            var b = shape.Bounds;

            Assert.InRange(anchor.Y, b.Top, b.Bottom);
        }
    }

    // ==================== Цвет ====================

    [Fact]
    public void Нагрузка_меняет_цвет_тела()
    {
        // Ради этого фигура и нужна: состояние читается одним взглядом, без
        // чтения цифр.
        Assert.NotEqual(Palette.PlateFor(Substance.Body, 0),
                        Palette.PlateFor(Substance.Body, 100));
    }

    [Fact]
    public void Спокойная_машина_холодная_а_загруженная_тёплая()
    {
        var спокойно = Palette.PlateFor(Substance.Body, 5);
        var загружено = Palette.PlateFor(Substance.Body, 95);

        Assert.True(спокойно.B > спокойно.R, "на спокойной машине фигура холодная");
        Assert.True(загружено.R > загружено.B, "на загруженной — тёплая");
    }

    [Fact]
    public void Свечение_не_бликует()
    {
        // У светящегося нет поверхности, которая отражала бы чужой свет.
        Assert.Equal(0, Palette.Gloss(Substance.Glow).Strength);
    }
}
