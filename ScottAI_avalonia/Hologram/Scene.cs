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
/// От этого зависит её цвет: фигура не украшение, а показания приборов.
/// Раньше в списке были ещё плащ и отделка — части, которые не показывали
/// ничего. Костюма нет, и каждая часть фигуры теперь занята делом.
/// </summary>
public enum BodyPart
{
    Head,
    Core,
    Torso,
    Arms,
    Legs,
}

/// <summary>
/// Из чего сделана грань.
///
/// Веществ два: тело и свечение. Пока фигура была в доспехах, их было семь —
/// сталь, маска, золото, сукно, подкладка, кожа, свечение, — и разделение
/// вещества и части тела было нужно, чтобы золочёный пояс и стальная кираса
/// красились по-разному, оставаясь одной частью. Костюма нет, и разделение
/// сохранилось только ради свечения: оно не отражает чужой свет и не
/// притеняется, в отличие от всего остального.
/// </summary>
public enum Substance
{
    /// <summary>Тело голограммы.</summary>
    Body,

    /// <summary>Светится само: свечение в груди.</summary>
    Glow,
}

/// <summary>Плоская грань: несколько вершин модели и то, что она показывает.</summary>
public sealed record Face(int[] Indices, BodyPart Part)
{
    /// <summary>Собственная яркость грани — ею задаётся объём у плоских деталей.</summary>
    public double Tint { get; init; } = 1.0;

    /// <summary>Из чего грань сделана: от этого цвет, блеск и прозрачность.</summary>
    public Substance Substance { get; init; } = Substance.Body;
}

/// <summary>Модель фигуры: вершины и грани.</summary>
public sealed class Mesh
{
    public List<Point3> Vertices { get; } = new();
    public List<Face> Faces { get; } = new();

    /// <summary>Из чего сделана часть тела, если вещество не названо прямо.</summary>
    public static Substance DefaultSubstance(BodyPart part) => part switch
    {
        BodyPart.Core => Substance.Glow,
        _ => Substance.Body,
    };

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
                       double lean = 0, Substance? substance = null)
    {
        var stuff = substance ?? DefaultSubstance(part);

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
                Substance = stuff,
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
                        double tint = 1.0, int sides = 8, bool capTop = true, bool capBottom = true,
                        Substance? substance = null)
    {
        if (rings.Count < 2) return;

        var stuff = substance ?? DefaultSubstance(part);

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

                Faces.Add(new Face(new[] { a, b, c, d }, part)
                {
                    Tint = tint * facing,
                    Substance = stuff,
                });
            }
        }

        // Крышки: без них труба просвечивает насквозь, и внутри видны её же
        // задние грани.
        if (capTop)
        {
            var top = new int[sides];
            for (var i = 0; i < sides; i++) top[i] = start + i;
            Array.Reverse(top);
            Faces.Add(new Face(top, part) { Tint = tint * 1.16, Substance = stuff });
        }

        if (capBottom)
        {
            var bottom = new int[sides];
            var last = (rings.Count - 1) * sides;
            for (var i = 0; i < sides; i++) bottom[i] = start + last + i;
            Faces.Add(new Face(bottom, part) { Tint = tint * 0.7, Substance = stuff });
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
    /// Наклонить вершины последней формы вокруг продольной оси фигуры.
    ///
    /// Наплечник сидит на плече под углом, а не лежит на нём плашмя; рука
    /// слегка отведена от корпуса. Строить их сразу под углом означало бы
    /// считать синусы в списке колец руками — наклонить готовое проще и
    /// понятнее.
    /// </summary>
    public void TiltLast(double degrees, double pivotX = 0, double pivotY = 0)
    {
        var angle = degrees * Math.PI / 180;
        var cos = Math.Cos(angle);
        var sin = Math.Sin(angle);

        for (var i = _lastShapeStart; i < Vertices.Count; i++)
        {
            var v = Vertices[i];
            var x = v.X - pivotX;
            var y = v.Y - pivotY;

            Vertices[i] = new Point3(
                pivotX + x * cos - y * sin,
                pivotY + x * sin + y * cos,
                v.Z);
        }
    }

    /// <summary>
    /// Поставить модель серединой в начало координат.
    ///
    /// Вращение и перспектива считаются относительно нуля, а модель вокруг него
    /// не строится: голова оказывается на отметке минус сто, ноги на плюс
    /// шестьдесят. Без этого фигура вращается вокруг пояса и уезжает из кадра
    /// тем сильнее, чем больше перспектива.
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

}

/// <summary>
/// Фигура, которой Scott показывает состояние машины.
///
/// Просто человек, без костюма. Доспех с плащом здесь был и получился, но
/// узнаваемая чужая внешность — юридический риск для продукта, который
/// собираются продавать, и «похожий костюм» его не снимает.
///
/// Без костюма фигура стала работать лучше по существу: цвет нагрузки больше
/// ни с чем не спорит и виден сразу, а раньше его приходилось приглушать,
/// чтобы металл оставался металлом.
///
/// Отметки по высоте взяты из пропорций человека, а не подобраны под размер
/// форм: голова — одна восьмая роста, середина роста приходится на пах, локоть
/// на талию, запястье на пах. Пока ноги были короче трёх голов, фигура
/// читалась куклой, сколько ни скругляй сечения.
/// </summary>
public static class Figure
{
    public static Mesh Build()
    {
        var mesh = new Mesh();

        // Перёд фигуры — со стороны отрицательного Z, там зритель. Правило
        // стоит держать: однажды перёд и зад уже были перепутаны, и фигура
        // стояла к человеку спиной.

        // ==================== Голова ====================
        //
        // Макушка на -100, подбородок на -80. Череп сужается кверху, у скул
        // шире всего, к подбородку сходит на нет.
        mesh.AddTube(BodyPart.Head, new[]
        {
            (-100.0, 4.5, 5.0),
            (-97.0, 8.0, 8.5),
            (-93.0, 9.5, 10.0),
            (-88.0, 9.8, 10.2),
            (-84.0, 9.0, 9.5),
            (-80.0, 6.5, 7.5),
        });

        // Шея: от подбородка до плеч.
        mesh.AddTube(BodyPart.Head, new[]
        {
            (-80.0, 4.6, 4.6),
            (-74.0, 5.2, 5.2),
            (-71.0, 6.4, 6.4),
        }, tint: 0.94);

        // ==================== Корпус ====================
        //
        // Сечение приплюснутое: грудная клетка шире, чем глубже. Талия уже
        // плеч и бёдер — на этом отношении человек и узнаётся, а не на числе
        // граней в сечении.
        mesh.AddTube(BodyPart.Torso, new[]
        {
            (-72.0, 13.5, 8.5),    // основание шеи
            (-66.0, 17.0, 10.0),   // плечевой пояс
            (-60.0, 17.5, 10.5),   // грудь
            (-52.0, 16.0, 10.0),
            (-42.0, 12.5, 8.5),    // талия
            (-32.0, 13.0, 9.0),
            (-24.0, 15.0, 10.0),   // бёдра
            (-18.0, 14.5, 9.5),
        });

        // Свечение в груди: общая загрузка процессора. Единственная деталь,
        // которой у человека нет, — и единственная, которая светится сама.
        mesh.AddTube(BodyPart.Core, new[]
        {
            (-63.0, 2.5, 2.0),
            (-60.0, 5.0, 4.0),
            (-57.0, 5.0, 4.0),
            (-54.0, 2.5, 2.0),
        }, tint: 1.6);

        mesh.ShiftLast(0, 0, -7);

        // ==================== Плечи и руки ====================
        foreach (var side in new[] { -1, 1 })
        {
            // Дельта плеча: округлая шапка. Без неё рука выглядит трубой,
            // вставленной в корпус.
            mesh.AddTube(BodyPart.Arms, new[]
            {
                (-71.0, 3.8, 4.2),
                (-68.0, 7.0, 7.5),
                (-64.0, 8.0, 8.5),
                (-59.0, 7.0, 7.5),
            });

            mesh.ShiftLast(side * 21, 0, 0);

            // Рука: плечо толще предплечья, локоть на уровне талии, запястье
            // на уровне паха.
            mesh.AddTube(BodyPart.Arms, new[]
            {
                (-62.0, 5.8, 5.8),
                (-52.0, 5.2, 5.2),
                (-45.0, 4.4, 4.4),
                (-42.0, 4.8, 4.8),   // локоть
                (-34.0, 4.4, 4.4),
                (-24.0, 3.8, 3.8),
                (-18.0, 3.4, 3.4),   // запястье
            }, tint: 0.97);

            mesh.ShiftLast(side * 24, 0, 0);
            mesh.TiltLast(side * 4, side * 24, -62);

            // Кисть
            mesh.AddTube(BodyPart.Arms, new[]
            {
                (-17.0, 3.2, 3.4),
                (-14.0, 3.8, 4.6),
                (-10.0, 3.6, 4.6),
                (-6.0, 2.6, 3.4),
            }, tint: 0.93);

            mesh.ShiftLast(side * 26, 0, -1);
        }

        // ==================== Ноги ====================
        //
        // От паха до пола — половина роста. Колени на +18, щиколотки на +52.
        foreach (var side in new[] { -1, 1 })
        {
            mesh.AddTube(BodyPart.Legs, new[]
            {
                (-16.0, 7.6, 7.6),   // бедро
                (-4.0, 7.0, 7.0),
                (8.0, 5.8, 6.0),
                (16.0, 5.2, 5.4),
                (19.0, 5.8, 6.0),    // колено
                (26.0, 5.2, 5.4),
                (38.0, 4.4, 4.8),
                (50.0, 3.4, 4.0),    // щиколотка
            });

            mesh.ShiftLast(side * 8, 0, 0);

            // Икра: утолщение сзади, а не по кругу. Ровная труба от колена до
            // щиколотки выглядит палкой — голень сужается не сразу.
            mesh.AddTube(BodyPart.Legs, new[]
            {
                (23.0, 3.6, 2.8),
                (28.0, 5.0, 4.2),
                (34.0, 4.6, 3.8),
                (40.0, 3.2, 2.6),
            }, tint: 0.95);

            mesh.ShiftLast(side * 8, 0, 3.2);

            // Стопа: вытянута вперёд, оттого нога перестаёт быть столбиком.
            mesh.AddTube(BodyPart.Legs, new[]
            {
                (50.0, 3.6, 4.4),
                (54.0, 4.2, 7.0),
                (58.0, 4.4, 8.5),
                (60.0, 3.8, 8.0),
            }, tint: 0.97);

            mesh.ShiftLast(side * 8, 0, -4);
        }

        mesh.Center();
        return mesh;
    }
}
