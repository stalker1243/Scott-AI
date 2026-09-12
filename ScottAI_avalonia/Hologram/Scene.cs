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
    /// <summary>Собственная яркость грани — ею задаётся объём у плоских деталей.</summary>
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
    /// Коробками собрано почти всё: шлем, кираса, наручи, поножи. Это не лень:
    /// латный доспех и состоит из плоских пластин, а сглаженные формы на фигуре
    /// в двести пикселей всё равно неразличимы.
    /// </summary>
    public void AddBox(Point3 center, double width, double height, double depth,
                       BodyPart part, double tint = 1.0, double taper = 1.0,
                       double lean = 0)
    {
        var hw = width / 2;
        var hh = height / 2;
        var hd = depth / 2;

        // Сужение книзу: с ним кираса перестаёт быть ящиком и становится
        // торсом, а нога — ногой.
        var bw = hw * taper;
        var bd = hd * taper;

        var start = Vertices.Count;

        // Верх
        Vertices.Add(new Point3(center.X - hw, center.Y - hh, center.Z - hd + lean));
        Vertices.Add(new Point3(center.X + hw, center.Y - hh, center.Z - hd + lean));
        Vertices.Add(new Point3(center.X + hw, center.Y - hh, center.Z + hd + lean));
        Vertices.Add(new Point3(center.X - hw, center.Y - hh, center.Z + hd + lean));

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

        // Центруем по доспеху, а не по всей модели. Плащ висит за спиной и
        // свисает ниже ног: считая по нему, середина коробки приходится не
        // туда, где человек видит фигуру, и она уезжает вбок и вверх.
        var body = new HashSet<int>();
        foreach (var face in Faces)
        {
            if (face.Part == BodyPart.Cape) continue;
            foreach (var index in face.Indices) body.Add(index);
        }

        if (body.Count == 0)
        {
            for (var i = 0; i < Vertices.Count; i++) body.Add(i);
        }

        double minX = double.MaxValue, maxX = double.MinValue;
        double minY = double.MaxValue, maxY = double.MinValue;
        double minZ = double.MaxValue, maxZ = double.MinValue;

        foreach (var index in body)
        {
            var v = Vertices[index];
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
    public void AddCape(double top, double height, double halfWidth, double depth, int segments = 8)
    {
        var rows = segments;
        var columns = segments;
        var start = Vertices.Count;

        for (var row = 0; row <= rows; row++)
        {
            var t = (double)row / rows;
            var y = top + height * t;

            // Книзу плащ расходится, а его нижний край отходит назад — так он
            // выглядит висящим и тяжёлым, а не приклеенным к спине.
            var spread = halfWidth * (0.55 + 0.45 * t * t);
            var back = depth * (0.3 + 0.7 * t);

            for (var column = 0; column <= columns; column++)
            {
                var u = (double)column / columns * 2 - 1;

                // Дуга поперёк: середина ближе к спине, края отходят вперёд,
                // будто плащ облегает плечи. Заворот небольшой намеренно —
                // ткань не должна выходить перед грудью, там ядро, и закрывать
                // его нечем.
                var curve = (1 - u * u) * depth * 0.28;

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
                var fold = 0.78 + 0.22 * ((column % 2 == 0) ? 1 : 0);

                Faces.Add(new Face(new[] { a, b, c, d }, BodyPart.Cape) { Tint = fold });
            }
        }
    }
}

/// <summary>
/// Фигура, которой Scott показывает состояние машины.
///
/// Латный доспех с капюшоном, глухой маской и тяжёлым плащом. Это устоявшийся
/// образ фантастики — закованный в броню человек в плаще, — а не чей-то
/// персонаж: узнаваемых эмблем, имён и точных повторений чужих костюмов здесь
/// нет намеренно. Программу предполагается продавать, и фигура на её главной
/// странице должна принадлежать ей самой.
/// </summary>
public static class Suits
{
    /// <summary>Собрать фигуру.</summary>
    public static Mesh Build()
    {
        var mesh = new Mesh();

        // ==================== Плащ ====================
        //
        // Строится первым: при равной глубине грани рисуются в порядке
        // добавления, и плащ должен оказаться позади фигуры, а не поверх неё.
        mesh.AddCape(top: -66, height: 100, halfWidth: 31, depth: 24);

        // Воротник: высокий, стоячий, из отдельных зубцов. Именно он делает
        // силуэт властным — без него фигура просто человек в накидке. Зубцами,
        // а не двумя брусками: из них и берётся ощущение кованой вещи.
        for (var i = 0; i < 5; i++)
        {
            var side = i - 2;
            var x = side * 9.5;
            var height = 30 - Math.Abs(side) * 5;

            mesh.AddBox(new Point3(x, -78 + Math.Abs(side) * 2.5, -13),
                        7, height, 7, BodyPart.Cape,
                        tint: 1.14 - Math.Abs(side) * 0.04, lean: -5);
        }

        // ==================== Голова ====================
        //
        // Капюшон облегает череп, из-под него выступает глухая маска. Шлем
        // гранёный: лоб, скулы и подбородок отдельными пластинами.
        mesh.AddBox(new Point3(0, -88, -4), 22, 19, 22, BodyPart.Cape, tint: 0.96, taper: 1.02);
        mesh.AddBox(new Point3(0, -78, -6), 21, 14, 20, BodyPart.Cape, tint: 0.9, taper: 0.92);

        // Лоб маски
        mesh.AddBox(new Point3(0, -90, 7), 17, 9, 10, BodyPart.Head, tint: 1.12, taper: 1.04);

        // Прорезь для глаз — единственная яркая деталь на лице.
        mesh.AddBox(new Point3(0, -85, 12), 13, 3, 4, BodyPart.Head, tint: 1.85);

        // Скулы
        mesh.AddBox(new Point3(-7, -80, 9), 6, 12, 9, BodyPart.Head, tint: 1.06, taper: 0.86);
        mesh.AddBox(new Point3(7, -80, 9), 6, 12, 9, BodyPart.Head, tint: 1.06, taper: 0.86);

        // Подбородок: сужается книзу, отчего маска перестаёт быть коробкой.
        mesh.AddBox(new Point3(0, -74, 8), 13, 9, 9, BodyPart.Head, tint: 0.98, taper: 0.62);

        // Горловое кольцо
        mesh.AddBox(new Point3(0, -68, 0), 12, 5, 12, BodyPart.Trim, tint: 1.1);

        // ==================== Наплечники ====================
        //
        // По три пластины на каждый, уступами — как настоящие. Одной коробкой
        // они выглядели ящиками на плечах.
        foreach (var side in new[] { -1, 1 })
        {
            mesh.AddBox(new Point3(side * 27, -62, 0), 20, 9, 21, BodyPart.Arms, tint: 1.16, taper: 0.92);
            mesh.AddBox(new Point3(side * 29, -55, 0), 19, 8, 20, BodyPart.Arms, tint: 1.04, taper: 0.9);
            mesh.AddBox(new Point3(side * 30, -49, 0), 17, 7, 18, BodyPart.Arms, tint: 0.94, taper: 0.88);
        }

        // ==================== Руки ====================
        foreach (var side in new[] { -1, 1 })
        {
            mesh.AddBox(new Point3(side * 30, -41, 0), 12, 14, 12, BodyPart.Arms, taper: 0.9);

            // Налокотник
            mesh.AddBox(new Point3(side * 30, -33, 0), 13, 6, 13, BodyPart.Arms, tint: 1.18);

            // Наруч
            mesh.AddBox(new Point3(side * 30, -25, 0), 11, 13, 11, BodyPart.Arms, tint: 1.02, taper: 0.92);

            // Латная перчатка
            mesh.AddBox(new Point3(side * 30, -17, 1), 10, 7, 12, BodyPart.Arms, tint: 1.1);
        }

        // ==================== Кираса ====================
        mesh.AddBox(new Point3(0, -58, 0), 34, 14, 21, BodyPart.Torso, tint: 1.08, taper: 0.98);

        // Грудные пластины: две, с разворотом — центр груди выступает вперёд.
        mesh.AddBox(new Point3(-9, -50, 3), 17, 16, 19, BodyPart.Torso, tint: 1.02, taper: 0.96);
        mesh.AddBox(new Point3(9, -50, 3), 17, 16, 19, BodyPart.Torso, tint: 1.02, taper: 0.96);

        // Набрюшник
        mesh.AddBox(new Point3(0, -36, 0), 29, 16, 18, BodyPart.Torso, tint: 0.94, taper: 0.84);
        mesh.AddBox(new Point3(0, -25, 0), 25, 10, 16, BodyPart.Torso, tint: 0.88, taper: 0.86);

        // Ядро в груди: обод и само свечение.
        mesh.AddBox(new Point3(0, -52, 12), 13, 13, 3, BodyPart.Trim, tint: 1.2);
        mesh.AddBox(new Point3(0, -52, 13), 8, 8, 3, BodyPart.Core, tint: 1.9);

        // ==================== Пояс ====================
        mesh.AddBox(new Point3(0, -18, 0), 27, 7, 17, BodyPart.Trim, tint: 1.16);
        mesh.AddBox(new Point3(0, -18, 9), 9, 9, 4, BodyPart.Trim, tint: 1.3);   // пряжка

        // Набедренные пластины
        foreach (var side in new[] { -1, 1 })
        {
            mesh.AddBox(new Point3(side * 11, -9, 1), 12, 13, 14, BodyPart.Trim, tint: 1.0, taper: 0.82);
        }

        // ==================== Ноги ====================
        foreach (var side in new[] { -1, 1 })
        {
            mesh.AddBox(new Point3(side * 10, 4, 0), 13, 22, 13, BodyPart.Legs, taper: 0.9);

            // Наколенник
            mesh.AddBox(new Point3(side * 10, 17, 1), 13, 8, 14, BodyPart.Legs, tint: 1.2);

            // Поножи
            mesh.AddBox(new Point3(side * 10, 29, 0), 11, 18, 12, BodyPart.Legs, tint: 1.0, taper: 0.9);

            // Сабатон: вытянут вперёд, оттого нога перестаёт быть столбиком.
            mesh.AddBox(new Point3(side * 10, 40, 2), 11, 5, 15, BodyPart.Legs, tint: 1.1);
            mesh.AddBox(new Point3(side * 10, 44, 5), 10, 4, 18, BodyPart.Legs, tint: 0.95);
        }

        mesh.Center();
        return mesh;
    }
}
