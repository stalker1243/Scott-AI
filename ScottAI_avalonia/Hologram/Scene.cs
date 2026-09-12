using System;
using System.Collections.Generic;
using System.Linq;

namespace ScottAI.Avalonia.Hologram;

/// <summary>Точка в пространстве модели.</summary>
public readonly record struct Point3(double X, double Y, double Z)
{
    public static Point3 operator +(Point3 a, Point3 b) => new(a.X + b.X, a.Y + b.Y, a.Z + b.Z);
    public static Point3 operator -(Point3 a, Point3 b) => new(a.X - b.X, a.Y - b.Y, a.Z - b.Z);

    /// <summary>Векторное произведение — нужно для нормали грани.</summary>
    public Point3 Cross(Point3 other) => new(
        Y * other.Z - Z * other.Y,
        Z * other.X - X * other.Z,
        X * other.Y - Y * other.X);

    public double Length => Math.Sqrt(X * X + Y * Y + Z * Z);
}

/// <summary>
/// Какой подсистеме принадлежит грань.
///
/// От этого зависит её цвет: фигура не украшение, а показания приборов. Плащ и
/// отделка живут отдельно — они ничего не показывают и красятся нейтрально,
/// иначе каждая складка спорила бы с показаниями за внимание.
/// </summary>
public enum BodyPart
{
    Head,
    Core,
    Torso,
    Arms,
    Legs,
    Cape,
    Trim,
}

/// <summary>Плоская грань: несколько вершин модели и то, что она показывает.</summary>
public sealed record Face(int[] Indices, BodyPart Part)
{
    /// <summary>Собственная яркость грани — им задаётся объём у плоских деталей.</summary>
    public double Tint { get; init; } = 1.0;
}

/// <summary>Модель фигуры: вершины и грани.</summary>
public sealed class Mesh
{
    public List<Point3> Vertices { get; } = new();
    public List<Face> Faces { get; } = new();

    /// <summary>
    /// Добавить коробку — основной строительный блок фигуры.
    ///
    /// Коробками собрано почти всё: голова, корпус, руки, ноги. Это не лень:
    /// гранёная броня из коробок и должна выглядеть гранёной, а сглаженные
    /// формы на такой мелкой фигуре всё равно неразличимы.
    /// </summary>
    public void AddBox(Point3 center, double width, double height, double depth,
                       BodyPart part, double tint = 1.0, double taper = 1.0)
    {
        var hw = width / 2;
        var hh = height / 2;
        var hd = depth / 2;

        // Сужение книзу: с ним корпус перестаёт быть ящиком и становится
        // торсом, а нога — ногой.
        var bw = hw * taper;
        var bd = hd * taper;

        var start = Vertices.Count;

        // Верх
        Vertices.Add(new Point3(center.X - hw, center.Y - hh, center.Z - hd));
        Vertices.Add(new Point3(center.X + hw, center.Y - hh, center.Z - hd));
        Vertices.Add(new Point3(center.X + hw, center.Y - hh, center.Z + hd));
        Vertices.Add(new Point3(center.X - hw, center.Y - hh, center.Z + hd));

        // Низ
        Vertices.Add(new Point3(center.X - bw, center.Y + hh, center.Z - bd));
        Vertices.Add(new Point3(center.X + bw, center.Y + hh, center.Z - bd));
        Vertices.Add(new Point3(center.X + bw, center.Y + hh, center.Z + bd));
        Vertices.Add(new Point3(center.X - bw, center.Y + hh, center.Z + bd));

        void Quad(int a, int b, int c, int d, double faceTint) =>
            Faces.Add(new Face(new[] { start + a, start + b, start + c, start + d }, part)
            {
                Tint = tint * faceTint,
            });

        // Небольшая разница в яркости между сторонами заменяет настоящий свет:
        // без неё коробка при повороте выглядит плоским пятном.
        Quad(0, 1, 2, 3, 1.15);   // верх
        Quad(7, 6, 5, 4, 0.72);   // низ
        Quad(0, 4, 5, 1, 1.00);   // зад
        Quad(3, 2, 6, 7, 1.00);   // перед
        Quad(0, 3, 7, 4, 0.86);   // левый бок
        Quad(1, 5, 6, 2, 0.86);   // правый бок
    }

    /// <summary>
    /// Поставить модель серединой в начало координат.
    ///
    /// Вращение и перспектива считаются относительно нуля, а модель вокруг него
    /// не строится: голова оказывается на отметке минус девяносто, ноги на плюс
    /// шестьдесят. Без этого фигура вращается вокруг пояса и уезжает из кадра
    /// тем сильнее, чем больше перспектива.
    ///
    /// По глубине центровка отдельная: плащ висит за спиной и смещает фигуру
    /// вперёд, из-за чего она при повороте «ныряла» под кольца проекции.
    /// </summary>
    public void Center()
    {
        if (Vertices.Count == 0) return;

        double minX = double.MaxValue, maxX = double.MinValue;
        double minY = double.MaxValue, maxY = double.MinValue;
        double minZ = double.MaxValue, maxZ = double.MinValue;

        foreach (var v in Vertices)
        {
            minX = Math.Min(minX, v.X); maxX = Math.Max(maxX, v.X);
            minY = Math.Min(minY, v.Y); maxY = Math.Max(maxY, v.Y);
            minZ = Math.Min(minZ, v.Z); maxZ = Math.Max(maxZ, v.Z);
        }

        var shift = new Point3((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2);

        for (var i = 0; i < Vertices.Count; i++)
        {
            Vertices[i] = Vertices[i] - shift;
        }
    }

    /// <summary>
    /// Добавить полотнище — плащ.
    ///
    /// Это сетка четырёхугольников, изогнутая по дуге: плоский прямоугольник за
    /// спиной читался бы как доска, а не как ткань.
    /// </summary>
    public void AddCape(double top, double height, double halfWidth, double depth, int segments = 7)
    {
        var rows = segments;
        var columns = segments;
        var start = Vertices.Count;

        for (var row = 0; row <= rows; row++)
        {
            var t = (double)row / rows;
            var y = top + height * t;

            // Книзу плащ расходится, а его нижний край слегка отходит назад —
            // так он выглядит висящим, а не приклеенным.
            var spread = halfWidth * (0.62 + 0.38 * t);
            var back = depth * (0.35 + 0.65 * t);

            for (var column = 0; column <= columns; column++)
            {
                var u = (double)column / columns * 2 - 1;

                // Дуга поперёк: середина ближе к спине, края отходят вперёд.
                var curve = (1 - u * u) * depth * 0.45;

                Vertices.Add(new Point3(u * spread, y, back - curve));
            }
        }

        for (var row = 0; row < rows; row++)
        {
            for (var column = 0; column < columns; column++)
            {
                var a = start + row * (columns + 1) + column;
                var b = a + 1;
                var c = a + columns + 2;
                var d = a + columns + 1;

                // Вертикальные полосы разной яркости: так на ткани появляются
                // складки, хотя геометрия у неё гладкая.
                var fold = 0.82 + 0.18 * ((column % 2 == 0) ? 1 : 0);

                Faces.Add(new Face(new[] { a, b, c, d }, BodyPart.Cape) { Tint = fold });
            }
        }
    }
}

/// <summary>
/// Костюм: какой фигурой Scott показывает состояние машины.
///
/// Два вида сделаны не ради разнообразия, а потому что это первое, что человек
/// показывает другим, открыв программу. Оба собраны из собственных форм: тяжёлая
/// броня и фигура в плаще — обычный язык фантастики, а не чей-то персонаж.
/// </summary>
public enum SuitKind
{
    /// <summary>Тяжёлая броня: широкие плечи, гранёные пластины, ядро в груди.</summary>
    Armor,

    /// <summary>Фигура в плаще: глухая маска, капюшон, полотнище за спиной.</summary>
    Cloak,
}

public static class Suits
{
    /// <summary>Собрать фигуру выбранного вида.</summary>
    public static Mesh Build(SuitKind kind) => kind switch
    {
        SuitKind.Cloak => BuildCloak(),
        _ => BuildArmor(),
    };

    /// <summary>
    /// Тяжёлая броня.
    ///
    /// Плечи намеренно шире бёдер: этот силуэт читается как «броня» даже когда
    /// фигура размером с ноготь, а детали ещё неразличимы.
    /// </summary>
    private static Mesh BuildArmor()
    {
        var mesh = new Mesh();

        // Голова заметно меньше корпуса: с крупной головой фигура читается как
        // игрушка, а не как броня.
        mesh.AddBox(new Point3(0, -84, 0), 19, 20, 19, BodyPart.Head, taper: 0.9);
        mesh.AddBox(new Point3(0, -80, 10), 13, 5, 4, BodyPart.Head, tint: 1.4);   // забрало
        mesh.AddBox(new Point3(0, -71, 0), 9, 6, 9, BodyPart.Trim);                // шея

        // Наплечники — то, по чему броню узнают с расстояния. Они шире груди и
        // выступают вверх, иначе силуэт остаётся человеческим, а не броневым.
        mesh.AddBox(new Point3(-30, -58, 0), 22, 16, 24, BodyPart.Arms, taper: 0.8);
        mesh.AddBox(new Point3(30, -58, 0), 22, 16, 24, BodyPart.Arms, taper: 0.8);

        // Грудь широкая, пояс узкий: это и есть весь силуэт.
        mesh.AddBox(new Point3(0, -54, 0), 42, 26, 24, BodyPart.Torso, taper: 0.88);
        mesh.AddBox(new Point3(0, -30, 0), 34, 26, 20, BodyPart.Torso, taper: 0.72);

        // Ядро в груди
        mesh.AddBox(new Point3(0, -54, 12), 11, 11, 4, BodyPart.Core, tint: 1.6);

        // Руки вынесены за корпус, чтобы не сливаться с ним.
        mesh.AddBox(new Point3(-32, -38, 0), 12, 26, 12, BodyPart.Arms, taper: 0.85);
        mesh.AddBox(new Point3(32, -38, 0), 12, 26, 12, BodyPart.Arms, taper: 0.85);
        mesh.AddBox(new Point3(-32, -18, 0), 10, 16, 10, BodyPart.Arms);
        mesh.AddBox(new Point3(32, -18, 0), 10, 16, 10, BodyPart.Arms);

        mesh.AddBox(new Point3(0, -14, 0), 26, 7, 17, BodyPart.Trim);

        // Ноги
        mesh.AddBox(new Point3(-10, 8, 0), 14, 36, 14, BodyPart.Legs, taper: 0.85);
        mesh.AddBox(new Point3(10, 8, 0), 14, 36, 14, BodyPart.Legs, taper: 0.85);
        mesh.AddBox(new Point3(-10, 34, 0), 12, 20, 13, BodyPart.Legs, taper: 0.9);
        mesh.AddBox(new Point3(10, 34, 0), 12, 20, 13, BodyPart.Legs, taper: 0.9);
        mesh.AddBox(new Point3(-10, 46, 3), 12, 6, 18, BodyPart.Legs);
        mesh.AddBox(new Point3(10, 46, 3), 12, 6, 18, BodyPart.Legs);

        mesh.Center();
        return mesh;
    }

    /// <summary>
    /// Фигура в плаще.
    ///
    /// Силуэт противоположен броне: узкие плечи, глухая маска, тяжёлое
    /// полотнище за спиной. Плащ строится первым, чтобы при равной глубине
    /// оказаться позади фигуры, а не поверх неё.
    /// </summary>
    private static Mesh BuildCloak()
    {
        var mesh = new Mesh();

        mesh.AddCape(top: -66, height: 112, halfWidth: 34, depth: 24);

        // Капюшон закрывает голову целиком, маска выступает вперёд.
        mesh.AddBox(new Point3(0, -86, -2), 24, 26, 25, BodyPart.Cape, tint: 0.92, taper: 1.1);
        mesh.AddBox(new Point3(0, -83, 11), 15, 19, 7, BodyPart.Head, taper: 0.92);
        mesh.AddBox(new Point3(0, -86, 15), 11, 4, 3, BodyPart.Head, tint: 1.5);   // прорезь глаз
        mesh.AddBox(new Point3(0, -70, 0), 10, 6, 10, BodyPart.Trim);

        // Наплечники плаща: узнаваемы в профиль, но уже, чем у брони.
        mesh.AddBox(new Point3(-23, -60, 0), 17, 11, 20, BodyPart.Cape, tint: 1.06, taper: 0.78);
        mesh.AddBox(new Point3(23, -60, 0), 17, 11, 20, BodyPart.Cape, tint: 1.06, taper: 0.78);

        mesh.AddBox(new Point3(0, -54, 0), 32, 26, 20, BodyPart.Torso, taper: 0.92);
        mesh.AddBox(new Point3(0, -30, 0), 29, 26, 18, BodyPart.Torso, taper: 0.78);
        mesh.AddBox(new Point3(0, -54, 10), 9, 9, 4, BodyPart.Core, tint: 1.6);

        // Руки прижаты к телу — из-под плаща торчать нечему.
        mesh.AddBox(new Point3(-21, -40, 0), 10, 26, 10, BodyPart.Arms, taper: 0.88);
        mesh.AddBox(new Point3(21, -40, 0), 10, 26, 10, BodyPart.Arms, taper: 0.88);

        mesh.AddBox(new Point3(0, -14, 0), 24, 6, 16, BodyPart.Trim);

        mesh.AddBox(new Point3(-9, 8, 0), 13, 36, 13, BodyPart.Legs, taper: 0.85);
        mesh.AddBox(new Point3(9, 8, 0), 13, 36, 13, BodyPart.Legs, taper: 0.85);
        mesh.AddBox(new Point3(-9, 34, 0), 11, 20, 12, BodyPart.Legs, taper: 0.9);
        mesh.AddBox(new Point3(9, 34, 0), 11, 20, 12, BodyPart.Legs, taper: 0.9);

        mesh.Center();
        return mesh;
    }
}
