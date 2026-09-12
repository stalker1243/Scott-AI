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
        // Уже плеч и выше ступней: плащ обрамляет фигуру, а не прячет её, и не
        // должен пересекаться с кольцами проекции у ног.
        mesh.AddCape(top: -66, height: 100, halfWidth: 31, depth: 24);

        // Воротник: высокий, стоячий, за головой. Именно он делает силуэт
        // тяжёлым и «властным» — без него фигура просто человек в накидке.
        mesh.AddBox(new Point3(-16, -80, -12), 10, 34, 10, BodyPart.Cape, tint: 1.12, lean: -6);
        mesh.AddBox(new Point3(16, -80, -12), 10, 34, 10, BodyPart.Cape, tint: 1.12, lean: -6);
        mesh.AddBox(new Point3(0, -74, -15), 34, 22, 8, BodyPart.Cape, tint: 0.96);

        // ==================== Голова ====================
        //
        // Капюшон закрывает череп целиком, из-под него выступает глухая маска.
        mesh.AddBox(new Point3(0, -86, -2), 23, 25, 24, BodyPart.Cape, tint: 0.94, taper: 1.06);
        mesh.AddBox(new Point3(0, -84, 10), 17, 22, 8, BodyPart.Head, taper: 0.94);

        // Прорезь для глаз — единственная яркая деталь на лице.
        mesh.AddBox(new Point3(0, -88, 14), 12, 3, 3, BodyPart.Head, tint: 1.7);

        // Скулы маски: две пластины по бокам, чтобы лицо не было плоским.
        mesh.AddBox(new Point3(-8, -82, 11), 4, 16, 6, BodyPart.Head, tint: 1.15);
        mesh.AddBox(new Point3(8, -82, 11), 4, 16, 6, BodyPart.Head, tint: 1.15);

        mesh.AddBox(new Point3(0, -69, 0), 11, 7, 11, BodyPart.Trim);

        // ==================== Плечи и руки ====================
        //
        // Наплечники широкие и приподнятые: силуэт должен читаться как доспех
        // даже когда фигура размером с ноготь и деталей ещё не видно.
        mesh.AddBox(new Point3(-28, -60, 0), 21, 14, 23, BodyPart.Arms, tint: 1.05, taper: 0.76);
        mesh.AddBox(new Point3(28, -60, 0), 21, 14, 23, BodyPart.Arms, tint: 1.05, taper: 0.76);

        mesh.AddBox(new Point3(-30, -44, 0), 12, 22, 12, BodyPart.Arms, taper: 0.88);
        mesh.AddBox(new Point3(30, -44, 0), 12, 22, 12, BodyPart.Arms, taper: 0.88);

        // Наручи
        mesh.AddBox(new Point3(-30, -26, 0), 11, 16, 11, BodyPart.Arms, tint: 1.08);
        mesh.AddBox(new Point3(30, -26, 0), 11, 16, 11, BodyPart.Arms, tint: 1.08);

        // ==================== Кираса ====================
        mesh.AddBox(new Point3(0, -54, 0), 36, 26, 22, BodyPart.Torso, taper: 0.9);
        mesh.AddBox(new Point3(0, -31, 0), 31, 24, 19, BodyPart.Torso, taper: 0.76);

        // Ядро в груди
        mesh.AddBox(new Point3(0, -54, 11), 10, 10, 4, BodyPart.Core, tint: 1.7);

        // Пояс и набедренные пластины
        mesh.AddBox(new Point3(0, -16, 0), 27, 8, 17, BodyPart.Trim, tint: 1.1);
        mesh.AddBox(new Point3(-11, -8, 0), 12, 12, 14, BodyPart.Trim, taper: 0.85);
        mesh.AddBox(new Point3(11, -8, 0), 12, 12, 14, BodyPart.Trim, taper: 0.85);

        // ==================== Ноги ====================
        mesh.AddBox(new Point3(-10, 8, 0), 13, 30, 13, BodyPart.Legs, taper: 0.88);
        mesh.AddBox(new Point3(10, 8, 0), 13, 30, 13, BodyPart.Legs, taper: 0.88);

        // Наколенники
        mesh.AddBox(new Point3(-10, 24, 1), 12, 8, 13, BodyPart.Legs, tint: 1.12);
        mesh.AddBox(new Point3(10, 24, 1), 12, 8, 13, BodyPart.Legs, tint: 1.12);

        mesh.AddBox(new Point3(-10, 36, 0), 11, 18, 12, BodyPart.Legs, taper: 0.9);
        mesh.AddBox(new Point3(10, 36, 0), 11, 18, 12, BodyPart.Legs, taper: 0.9);

        // Сабатоны
        mesh.AddBox(new Point3(-10, 47, 3), 11, 6, 17, BodyPart.Legs);
        mesh.AddBox(new Point3(10, 47, 3), 11, 6, 17, BodyPart.Legs);

        mesh.Center();
        return mesh;
    }
}
