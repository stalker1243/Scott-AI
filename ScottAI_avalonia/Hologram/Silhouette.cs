using System;
using System.Collections.Generic;
using Avalonia;
using Avalonia.Media;

namespace ScottAI.Avalonia.Hologram;

/// <summary>
/// Человеческая фигура плоским силуэтом.
///
/// ПОЧЕМУ ПЛОСКО. Объёмная фигура была собрана из труб с многогранным
/// сечением, и форму задавали кольца — то есть окружности. Живое тело так не
/// устроено: у него нет ни одного круглого сечения, а силуэт состоит из дуг
/// разной кривизны, которые переходят друг в друга. На объёме это можно
/// изобразить, только подняв число граней до неприличного, и всё равно
/// останутся фасетки.
///
/// Плоский силуэт рисуется кривыми, а у кривой нет ни граней, ни колец.
/// Поэтому здесь форма получается точнее, а стоит заметно дешевле: вместо
/// тысячи граней на каждом кадре — десяток путей, и никакой сортировки по
/// глубине.
///
/// КООРДИНАТЫ. Фигура описана в собственной сетке: ноль по горизонтали —
/// середина, по вертикали — макушка. Рост ровно двести единиц, и все отметки
/// взяты из пропорций человека: голова — одна восьмая роста, середина роста
/// приходится на пах, локоть на талию, запястье на пах. Масштаб и положение
/// накладываются при отрисовке, поэтому фигура одинаково верна при любом
/// размере окна.
/// </summary>
public static class Silhouette
{
    /// <summary>Рост фигуры в её собственных единицах.</summary>
    public const double Height = 200;

    /// <summary>Половина ширины фигуры — по самым широким местам, плечам.</summary>
    public const double HalfWidth = 30;

    // Ключевые полуширины.
    //
    // Вынесены в именованные величины, а не вписаны в кривые числами: по ним
    // и строится контур, и проверяется, что силуэт остался человеческим.
    // Пока они жили внутри путей, проверить пропорции можно было только
    // пересечением фигур, а его Avalonia считает через графическую
    // подсистему, которой в проверках нет.
    public const double SkullHalf = 11.5;      // череп у скул
    public const double ShoulderHalf = 24;     // плечи, самое широкое место
    public const double WaistHalf = 17;        // талия
    public const double HipHalf = 19.5;        // бёдра

    // Отметки по высоте. Числа не подобраны на глаз: это канон восьми голов,
    // тот же, что использовался для объёмной фигуры.
    private const double Crown = 2;        // макушка
    private const double Chin = 26;        // подбородок
    private const double Shoulder = 42;    // линия плеч
    private const double Chest = 58;
    private const double Waist = 82;
    private const double Hip = 100;        // ровно середина роста
    private const double Knee = 143;
    private const double Ankle = 190;
    private const double Sole = 198;

    /// <summary>
    /// Части фигуры и их контуры.
    ///
    /// Порядок важен, и первая попытка его перепутала. Руки рисовались поверх
    /// корпуса, отчего внутренний край каждой проходил по груди отдельной
    /// линией и фигура выглядела крылатой. У человека этой линии не видно:
    /// рука прилегает к телу, и виден только наружный контур. Поэтому руки и
    /// ноги идут первыми, а корпус ложится поверх их внутренних краёв.
    ///
    /// Голова рисуется последней: шея должна уходить под плечи, а не
    /// обрываться на них.
    /// </summary>
    public static IReadOnlyList<(BodyPart Part, Geometry Shape)> Parts() => new[]
    {
        (BodyPart.Arms, Arm(-1)),
        (BodyPart.Arms, Arm(1)),
        (BodyPart.Legs, Leg(-1)),
        (BodyPart.Legs, Leg(1)),
        (BodyPart.Torso, Torso()),
        (BodyPart.Head, Head()),
    };

    /// <summary>
    /// Где поставить свечение, показывающее общую загрузку процессора.
    ///
    /// Середина груди: единственная точка, куда взгляд попадает сам, не ища.
    /// </summary>
    public static Point Core => new(0, Chest - 4);

    /// <summary>
    /// Голова с шеей.
    ///
    /// Череп — не овал: затылок круглый, скулы шире всего, к подбородку форма
    /// сходит на нет. Овал вместо этого даёт яйцо, и это сразу видно.
    ///
    /// Шея входит в этот же контур, а не начинается отдельной фигурой ниже
    /// подбородка: на первой живой проверке голова из-за этого выглядела
    /// отрезанной от тела.
    /// </summary>
    private static Geometry Head()
    {
        var g = new StreamGeometry();
        using var c = g.Open();

        // Левая половина сверху вниз, затем правая снизу вверх.
        c.BeginFigure(new Point(0, Crown), isFilled: true);

        c.CubicBezierTo(new Point(-7, Crown), new Point(-SkullHalf, 8), new Point(-SkullHalf, 13.5));
        c.CubicBezierTo(new Point(-SkullHalf, 18), new Point(-10.5, 21.5), new Point(-8, 24));
        c.CubicBezierTo(new Point(-6.5, 25.5), new Point(-5.5, Chin), new Point(-5, Chin + 1));

        // Шея расширяется книзу и уходит под плечи. Узкая: у человека она
        // заметно тоньше головы, и широкая сразу превращает фигуру в снеговика.
        c.CubicBezierTo(new Point(-4.5, 31), new Point(-5, 34), new Point(-5.5, 37));
        c.LineTo(new Point(5.5, 37));
        c.CubicBezierTo(new Point(5, 34), new Point(4.5, 31), new Point(5, Chin + 1));

        c.CubicBezierTo(new Point(5.5, Chin), new Point(6.5, 25.5), new Point(8, 24));
        c.CubicBezierTo(new Point(10.5, 21.5), new Point(SkullHalf, 18), new Point(SkullHalf, 13.5));
        c.CubicBezierTo(new Point(SkullHalf, 8), new Point(7, Crown), new Point(0, Crown));

        c.EndFigure(isClosed: true);
        return g;
    }

    /// <summary>
    /// Корпус: от плеч до паха.
    ///
    /// Три перегиба, без которых силуэт перестаёт быть человеческим: плечи
    /// сходят вниз пологой дугой, талия уходит внутрь, таз снова расходится.
    /// Прямая линия от плеча к бедру превращает фигуру в мешок, а угол на
    /// плече — в наплечник.
    /// </summary>
    private static Geometry Torso()
    {
        var g = new StreamGeometry();
        using var c = g.Open();

        c.BeginFigure(new Point(-6, 34), isFilled: true);

        // Трапеция и плечо: линия от шеи идёт вниз дугой, а не прямой.
        c.CubicBezierTo(new Point(-11, 36), new Point(-16, 38), new Point(-20, Shoulder));
        c.CubicBezierTo(new Point(-22.5, 44), new Point(-23.5, 47), new Point(-ShoulderHalf, 51));

        // Грудная клетка и талия.
        c.CubicBezierTo(new Point(-23, 60), new Point(-21, 70), new Point(-18.5, 76));
        c.CubicBezierTo(new Point(-17.5, 79), new Point(-WaistHalf, Waist), new Point(-WaistHalf, 86));

        // Таз расходится к бёдрам.
        c.CubicBezierTo(new Point(-17.5, 92), new Point(-19, 96), new Point(-HipHalf, Hip + 2));
        c.LineTo(new Point(HipHalf, Hip + 2));

        c.CubicBezierTo(new Point(19, 96), new Point(17.5, 92), new Point(WaistHalf, 86));
        c.CubicBezierTo(new Point(WaistHalf, Waist), new Point(17.5, 79), new Point(18.5, 76));
        c.CubicBezierTo(new Point(21, 70), new Point(23, 60), new Point(ShoulderHalf, 51));

        c.CubicBezierTo(new Point(23.5, 47), new Point(22.5, 44), new Point(20, Shoulder));
        c.CubicBezierTo(new Point(16, 38), new Point(11, 36), new Point(6, 34));

        c.EndFigure(isClosed: true);
        return g;
    }

    /// <summary>
    /// Рука от плеча до кончиков пальцев.
    ///
    /// У руки два разных участка: плечо толще, предплечье тоньше, между ними
    /// локоть. Ровный наружный край от плеча до кисти превращает руку в крыло
    /// — именно так и вышло на первой живой проверке.
    ///
    /// Рука идёт вдоль корпуса и слегка внутрь: у человека опущенная кисть
    /// приходится на середину бедра, а не висит в стороне.
    /// </summary>
    private static Geometry Arm(int side)
    {
        var g = new StreamGeometry();
        using var c = g.Open();

        double X(double v) => v * side;

        // Наружный край: плечо, локоть, предплечье.
        c.BeginFigure(new Point(X(19), 40), isFilled: true);

        c.CubicBezierTo(new Point(X(24), 43), new Point(X(26), 48), new Point(X(26), 55));
        c.CubicBezierTo(new Point(X(26), 64), new Point(X(25), 72), new Point(X(24), 79));

        // Локоть — небольшое утолщение на уровне талии.
        c.CubicBezierTo(new Point(X(24.5), Waist), new Point(X(24), 86), new Point(X(23), 90));
        c.CubicBezierTo(new Point(X(22), 95), new Point(X(21.5), Hip), new Point(X(21), 104));

        // Кисть: чуть шире запястья, пальцы намечены округлым краем.
        c.CubicBezierTo(new Point(X(22), 110), new Point(X(21.5), 117), new Point(X(19.5), 122));
        c.CubicBezierTo(new Point(X(18.5), 124.5), new Point(X(16.5), 124.5), new Point(X(15.5), 122));

        // Внутренний край: вверх к подмышке.
        c.CubicBezierTo(new Point(X(14.5), 117), new Point(X(15), 110), new Point(X(15.5), 104));
        c.CubicBezierTo(new Point(X(16), 95), new Point(X(17), 88), new Point(X(18), 79));
        c.CubicBezierTo(new Point(X(19), 72), new Point(X(20), 64), new Point(X(20), 56));
        c.CubicBezierTo(new Point(X(20), 50), new Point(X(19.5), 46), new Point(X(19), 44));

        c.EndFigure(isClosed: true);
        return g;
    }

    /// <summary>
    /// Нога от бедра до стопы.
    ///
    /// Икра толще сзади, щиколотка тонкая, стопа вытянута вперёд. Ровный конус
    /// от бедра к полу читается ходулей, а нога, обрывающаяся линией, —
    /// незаконченным рисунком: на первой проверке стоп не было вовсе.
    /// </summary>
    private static Geometry Leg(int side)
    {
        var g = new StreamGeometry();
        using var c = g.Open();

        double X(double v) => v * side;

        // Наружный край сверху вниз.
        c.BeginFigure(new Point(X(2.5), Hip), isFilled: true);

        c.CubicBezierTo(new Point(X(13), Hip), new Point(X(15.5), 108), new Point(X(15), 118));
        c.CubicBezierTo(new Point(X(14.5), 128), new Point(X(13), 137), new Point(X(12), Knee));

        // Икра и щиколотка.
        c.CubicBezierTo(new Point(X(11.5), 152), new Point(X(11), 160), new Point(X(9.5), 170));
        c.CubicBezierTo(new Point(X(8.5), 178), new Point(X(8), 185), new Point(X(7.5), Ankle));

        // Стопа: пятка сзади, носок вытянут вперёд. Вперёд — в сторону от
        // середины фигуры, чтобы обе стопы смотрели наружу, как у стоящего
        // человека с чуть разведёнными носками.
        c.CubicBezierTo(new Point(X(8.5), 193), new Point(X(11), 195), new Point(X(13.5), 196));
        c.CubicBezierTo(new Point(X(14.5), 196.5), new Point(X(14.5), Sole), new Point(X(13), Sole));
        c.LineTo(new Point(X(1.5), Sole));
        c.CubicBezierTo(new Point(X(0.5), 196), new Point(X(1), 193), new Point(X(2), Ankle));

        // Внутренний край снизу вверх.
        c.CubicBezierTo(new Point(X(2.5), 185), new Point(X(3), 178), new Point(X(3.5), 170));
        c.CubicBezierTo(new Point(X(4), 160), new Point(X(4.5), 152), new Point(X(4.5), Knee));
        c.CubicBezierTo(new Point(X(4.5), 137), new Point(X(3.5), 128), new Point(X(3), 118));
        c.CubicBezierTo(new Point(X(2.5), 110), new Point(X(2.5), Hip + 4), new Point(X(2.5), Hip));

        c.EndFigure(isClosed: true);
        return g;
    }

    /// <summary>
    /// Куда показывает выноска для каждой подсистемы.
    ///
    /// Точка берётся на самой части, а не рядом с ней: линия, упирающаяся в
    /// пустоту возле фигуры, заставляет гадать, о чём речь.
    /// </summary>
    public static Point Anchor(BodyPart part) => part switch
    {
        BodyPart.Head => new Point(0, 14),
        BodyPart.Torso => new Point(0, 70),
        BodyPart.Arms => new Point(23, 96),
        BodyPart.Legs => new Point(8, 150),
        _ => new Point(0, Chest),
    };
}
