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
    /// Коробка — это пластина доспеха: наплечник, налокотник, наколенник, пояс.
    /// Тут она на своём месте, латы и состоят из плоских пластин. Всё, что
    /// должно быть округлым — корпус, шея, руки, ноги, — собрано трубами, см.
    /// AddTube ниже.
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
        _lastShapeStart = start;

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
        // Перёд — со стороны отрицательного Z: перспектива считается как
        // D / (D + z), и точка тем дальше, чем больше Z. Эти две подписи
        // раньше стояли наоборот, и по ним фигура была собрана спиной к
        // зрителю — вместе с плащом, оттого он и проходил сквозь тело.
        Quad(0, 4, 5, 1, 1.00);   // перёд
        Quad(3, 2, 6, 7, 1.00);   // зад
        Quad(0, 3, 7, 4, 0.86);   // левый бок
        Quad(1, 5, 6, 2, 0.86);   // правый бок
    }

    /// <summary>
    /// Добавить трубу — форму, натянутую на кольца сечений.
    ///
    /// Основа всего, что должно быть округлым: шея, руки, ноги, корпус. Кольцо
    /// задаётся высотой и двумя полуосями — поперёк и в глубину, — поэтому
    /// сечение может быть и круглым, и приплюснутым, как у настоящей грудной
    /// клетки.
    ///
    /// Восьми граней в сечении достаточно. На фигуре в двести пикселей это уже
    /// читается как округлость, а больше граней означало бы вдвое больше работы
    /// на каждый кадр без видимой разницы.
    /// </summary>
    public void AddTube(BodyPart part, IReadOnlyList<(double Y, double RadiusX, double RadiusZ)> rings,
                        double tint = 1.0, int sides = 8, bool capTop = true, bool capBottom = true)
    {
        if (rings.Count < 2) return;

        var start = Vertices.Count;
        _lastShapeStart = start;

        foreach (var ring in rings)
        {
            for (var i = 0; i < sides; i++)
            {
                // Сечение повёрнуто на половину шага: так спереди оказывается
                // грань, а не ребро. Ребро посреди груди выглядит килем.
                var angle = (i + 0.5) * 2 * Math.PI / sides;

                Vertices.Add(new Point3(
                    Math.Sin(angle) * ring.RadiusX,
                    ring.Y,
                    Math.Cos(angle) * ring.RadiusZ));
            }
        }

        for (var level = 0; level < rings.Count - 1; level++)
        {
            for (var i = 0; i < sides; i++)
            {
                var next = (i + 1) % sides;

                var a = start + level * sides + i;
                var b = start + level * sides + next;
                var c = start + (level + 1) * sides + next;
                var d = start + (level + 1) * sides + i;

                // Боковые грани чуть темнее передних: свет падает наклонно, но
                // собственная разница делает форму заметнее на мелком размере.
                var angle = (i + 0.5) * 2 * Math.PI / sides;
                var facing = 0.86 + 0.14 * Math.Cos(angle);

                Faces.Add(new Face(new[] { a, b, c, d }, part) { Tint = tint * facing });
            }
        }

        // Крышки: без них труба просвечивает насквозь, и внутри видны её же
        // задние грани.
        if (capTop)
        {
            var top = new int[sides];
            for (var i = 0; i < sides; i++) top[i] = start + i;
            Array.Reverse(top);
            Faces.Add(new Face(top, part) { Tint = tint * 1.16 });
        }

        if (capBottom)
        {
            var bottom = new int[sides];
            var last = (rings.Count - 1) * sides;
            for (var i = 0; i < sides; i++) bottom[i] = start + last + i;
            Faces.Add(new Face(bottom, part) { Tint = tint * 0.7 });
        }
    }

    /// <summary>
    /// Сдвинуть вершины, добавленные последней формой.
    ///
    /// Труба строится вокруг вертикальной оси, а рука, нога и маска стоят в
    /// стороне от неё. Передавать смещение внутрь означало бы усложнять трубу
    /// ради нескольких случаев; проще подвинуть готовое.
    /// </summary>
    public void ShiftLast(double dx, double dy, double dz)
    {
        for (var i = _lastShapeStart; i < Vertices.Count; i++)
        {
            Vertices[i] = Vertices[i] + new Point3(dx, dy, dz);
        }
    }

    /// <summary>С какой вершины началась последняя добавленная форма.</summary>
    private int _lastShapeStart;

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

            // Плащ начинается позади кирасы и книзу отходит ещё дальше. Верхний
            // край намеренно вынесен за спину: раньше он висел почти на той же
            // глубине, что и корпус, и полотнище проходило сквозь тело при
            // любой дуге.
            var back = depth * (0.58 + 0.42 * t);

            // Ширина у плеч уже не меньше кирасы: заворачиваясь вперёд, края
            // должны проходить СНАРУЖИ корпуса, а не внутри него.
            var spread = halfWidth * (0.78 + 0.22 * t * t);

            for (var column = 0; column <= columns; column++)
            {
                var u = (double)column / columns * 2 - 1;

                // Дуга поперёк: середина дальше всех, края заворачиваются
                // вперёд. Заворот растёт книзу: у плеч плащ пришит и
                // лежит плоско, а ниже расходится. Без этого верхние углы
                // полотнища выезжают перед наплечниками и режут их.
                //
                // Здесь была вторая ошибка плаща: поправка считалась как
                // (1 - u²) и достигала наибольшего значения в СЕРЕДИНЕ.
                // Вычитаясь из глубины, она выносила середину полотнища
                // вперёд — прямо в спину, — а края оставляла позади.
                var wrap = u * u * depth * 0.33 * t;

                Vertices.Add(new Point3(u * spread, y, back - wrap));
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

                // Каждый кусок добавляется дважды, в обе стороны.
                //
                // У ткани нет толщины, а отрисовщик пропускает грани,
                // отвёрнутые от зрителя, — для замкнутых форм это верно, но
                // полотнище просто исчезало с одной из сторон. Плаща не было
                // видно спереди вообще.
                //
                // Изнанка темнее лицевой стороны: свет считается по нормали,
                // и без разницы обе стороны выглядели бы одинаково.
                Faces.Add(new Face(new[] { a, b, c, d }, BodyPart.Cape) { Tint = fold });
                Faces.Add(new Face(new[] { d, c, b, a }, BodyPart.Cape) { Tint = fold * 0.74 });
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

        // Перёд фигуры — со стороны отрицательного Z, там зритель. Плащ,
        // капюшон и воротник уходят в плюс, за спину. Держаться этого правила
        // важнее, чем кажется: однажды перёд и зад уже были перепутаны, и плащ
        // висел прямо поверх лица.

        // ==================== Плащ ====================
        //
        // Строится первым: при равной глубине грани рисуются в порядке
        // добавления, и плащ должен оказаться позади фигуры, а не поверх неё.
        mesh.AddCape(top: -66, height: 106, halfWidth: 33, depth: 26);

        // Воротник: высокий, стоячий, из отдельных зубцов. Именно он делает
        // силуэт властным — без него фигура просто человек в накидке.
        for (var i = 0; i < 5; i++)
        {
            var side = i - 2;

            mesh.AddBox(new Point3(side * 9, -78 + Math.Abs(side) * 2.5, 13),
                        6.5, 30 - Math.Abs(side) * 5, 6,
                        BodyPart.Cape, tint: 1.14 - Math.Abs(side) * 0.04, lean: 5);
        }

        // ==================== Голова ====================
        //
        // Череп — труба с кольцами: сверху сужается, у скул шире всего, к
        // подбородку сходит на нет. Коробка здесь читалась ящиком.
        mesh.AddTube(BodyPart.Cape, new[]
        {
            (-99.0, 4.5, 5.0),
            (-96.0, 9.0, 10.0),
            (-91.0, 11.5, 12.5),
            (-85.0, 11.5, 12.5),
            (-79.0, 10.0, 10.5),
        }, tint: 0.95);

        // Маска: выступает вперёд из-под капюшона, книзу сужается.
        mesh.AddTube(BodyPart.Head, new[]
        {
            (-93.0, 7.5, 6.5),
            (-88.0, 9.5, 8.5),
            (-83.0, 9.0, 8.0),
            (-77.0, 6.5, 6.5),
            (-73.0, 4.0, 4.5),
        }, tint: 1.06);

        mesh.ShiftLast(0, 0, -4);

        // Прорезь для глаз — единственная яркая деталь на лице.
        mesh.AddBox(new Point3(0, -86, -11), 13, 2.8, 3, BodyPart.Head, tint: 1.9);

        // Шея
        mesh.AddTube(BodyPart.Trim, new[]
        {
            (-75.0, 5.5, 5.5),
            (-66.0, 6.5, 6.5),
        }, tint: 1.06);

        // ==================== Корпус ====================
        //
        // Сечение приплюснутое: грудная клетка шире, чем глубже. Талия уже
        // плеч и бёдер — на этом отношении человек и узнаётся, а не на числе
        // граней в сечении.
        mesh.AddTube(BodyPart.Torso, new[]
        {
            (-64.0, 15.0, 9.5),    // основание шеи
            (-58.0, 18.5, 11.0),   // грудь
            (-50.0, 18.0, 11.0),
            (-40.0, 15.5, 10.0),   // рёбра сходятся
            (-30.0, 13.0, 9.0),    // талия
            (-22.0, 14.5, 9.5),    // бёдра расходятся
            (-14.0, 15.5, 10.0),
        });

        // Грудные пластины поверх корпуса
        mesh.AddBox(new Point3(-8.5, -54, -8), 15, 15, 7, BodyPart.Torso, tint: 1.14, taper: 0.9);
        mesh.AddBox(new Point3(8.5, -54, -8), 15, 15, 7, BodyPart.Torso, tint: 1.14, taper: 0.9);

        // Ядро в груди: обод и свечение.
        mesh.AddBox(new Point3(0, -52, -11), 12, 12, 3, BodyPart.Trim, tint: 1.22);
        mesh.AddBox(new Point3(0, -52, -13), 7, 7, 3, BodyPart.Core, tint: 1.95);

        // ==================== Плечи и руки ====================
        foreach (var side in new[] { -1, 1 })
        {
            // Наплечник: три пластины уступами. Здесь коробки на своём месте —
            // доспех и состоит из плоских пластин.
            mesh.AddBox(new Point3(side * 24, -62, 0), 19, 8, 19, BodyPart.Arms, tint: 1.18, taper: 0.94);
            mesh.AddBox(new Point3(side * 26, -56, 0), 18, 7, 18, BodyPart.Arms, tint: 1.06, taper: 0.92);
            mesh.AddBox(new Point3(side * 27, -50, 0), 16, 6, 16, BodyPart.Arms, tint: 0.96, taper: 0.9);

            // Рука: труба с утолщением у плеча и локтя.
            mesh.AddTube(BodyPart.Arms, new[]
            {
                (-54.0, 6.5, 6.5),
                (-45.0, 6.0, 6.0),
                (-37.0, 5.0, 5.0),
                (-33.0, 5.8, 5.8),   // локоть
                (-26.0, 4.8, 4.8),
                (-17.0, 4.2, 4.2),
            });

            mesh.ShiftLast(side * 27, 0, 0);

            // Налокотник и латная перчатка
            mesh.AddBox(new Point3(side * 27, -33, 0), 12, 5.5, 12, BodyPart.Arms, tint: 1.2);
            mesh.AddBox(new Point3(side * 27, -16, -1), 9, 7, 11, BodyPart.Arms, tint: 1.1, taper: 0.85);
        }

        // ==================== Пояс ====================
        mesh.AddBox(new Point3(0, -16, 0), 26, 6.5, 17, BodyPart.Trim, tint: 1.18);
        mesh.AddBox(new Point3(0, -16, -9), 8, 8, 3.5, BodyPart.Trim, tint: 1.32);   // пряжка

        foreach (var side in new[] { -1, 1 })
        {
            mesh.AddBox(new Point3(side * 10, -7, -1), 11, 12, 13, BodyPart.Trim, taper: 0.84);
        }

        // ==================== Ноги ====================
        foreach (var side in new[] { -1, 1 })
        {
            mesh.AddTube(BodyPart.Legs, new[]
            {
                (-10.0, 7.5, 7.5),   // бедро
                (2.0, 6.8, 6.8),
                (14.0, 5.6, 5.8),
                (18.0, 6.4, 6.6),    // колено
                (30.0, 5.0, 5.4),
                (40.0, 4.4, 5.0),    // щиколотка
            });

            mesh.ShiftLast(side * 9, 0, 0);

            // Наколенник
            mesh.AddBox(new Point3(side * 9, 18, -1), 12, 7, 13, BodyPart.Legs, tint: 1.22);

            // Сабатон: вытянут вперёд, оттого нога перестаёт быть столбиком.
            mesh.AddBox(new Point3(side * 9, 43, -3), 10, 5, 15, BodyPart.Legs, tint: 1.12);
            mesh.AddBox(new Point3(side * 9, 46, -6), 9, 3.5, 17, BodyPart.Legs, tint: 0.96);
        }

        mesh.Center();
        return mesh;
    }
}
