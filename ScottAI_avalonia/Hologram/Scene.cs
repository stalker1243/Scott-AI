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

/// <summary>
/// Из чего сделана грань.
///
/// От части тела это не зависит: кираса и наручи из одной стали, но пояс
/// золочёный, а плащ суконный. Материал задаёт цвет, блеск и прозрачность;
/// часть задаёт, какую нагрузку грань показывает. Смешивать их в одно свойство
/// уже пробовали — вся фигура выглядела отлитой из одного вещества.
/// </summary>
public enum Substance
{
    /// <summary>Вороненая сталь: кираса, наручи, поножи.</summary>
    Plate,

    /// <summary>Светлый металл маски — лицо должно читаться первым.</summary>
    Mask,

    /// <summary>Золочёная отделка: пояс, обод ядра, кромки наплечников.</summary>
    Gold,

    /// <summary>Сукно плаща — лицевая сторона.</summary>
    Cloth,

    /// <summary>Подкладка плаща: единственное тёплое пятно на фигуре.</summary>
    Lining,

    /// <summary>Кожа ремней и сочленений: матовая, тёмная.</summary>
    Leather,

    /// <summary>Светится сам: ядро в груди и прорезь для глаз.</summary>
    Glow,
}

/// <summary>Плоская грань: несколько вершин модели и то, что она показывает.</summary>
public sealed record Face(int[] Indices, BodyPart Part)
{
    /// <summary>Собственная яркость грани — ею задаётся объём у плоских деталей.</summary>
    public double Tint { get; init; } = 1.0;

    /// <summary>Из чего грань сделана: от этого цвет, блеск и прозрачность.</summary>
    public Substance Substance { get; init; } = Substance.Plate;
}

/// <summary>Модель фигуры: вершины и грани.</summary>
public sealed class Mesh
{
    public List<Point3> Vertices { get; } = new();
    public List<Face> Faces { get; } = new();

    /// <summary>
    /// Из чего сделана часть тела, если материал не назван прямо.
    ///
    /// Большинство деталей из того, что и ожидается: доспех стальной, плащ
    /// суконный, ядро светится. Называть материал у каждой формы означало бы
    /// повторять очевидное полсотни раз.
    /// </summary>
    public static Substance DefaultSubstance(BodyPart part) => part switch
    {
        BodyPart.Head => Substance.Mask,
        BodyPart.Core => Substance.Glow,
        BodyPart.Cape => Substance.Cloth,
        BodyPart.Trim => Substance.Gold,
        _ => Substance.Plate,
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
                Faces.Add(new Face(new[] { a, b, c, d }, BodyPart.Cape)
                {
                    Tint = fold,
                    Substance = Substance.Cloth,
                });

                Faces.Add(new Face(new[] { d, c, b, a }, BodyPart.Cape)
                {
                    Tint = fold * 0.9,
                    Substance = Substance.Lining,
                });
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
        //
        // Отметки по высоте взяты из пропорций человека, а не подобраны под
        // размер форм: голова — одна восьмая роста, середина роста приходится
        // на пах. Пока ноги были короче трёх голов, фигура читалась куклой,
        // сколько ни скругляй сечения.

        // ==================== Плащ ====================
        //
        // Строится первым: при равной глубине грани рисуются в порядке
        // добавления, и плащ должен оказаться позади фигуры, а не поверх неё.
        mesh.AddCape(top: -70, height: 118, halfWidth: 30, depth: 28);

        // Воротник: высокий, стоячий, из отдельных зубцов. Именно он делает
        // силуэт властным — без него фигура просто человек в накидке.
        for (var i = 0; i < 5; i++)
        {
            var side = i - 2;
            // Зубец ниже головы. Сначала он был с неё ростом и превращал
            // воротник в забор за спиной, рядом с которым голова терялась.
            var height = 18 - Math.Abs(side) * 4;
            var top = -78 + Math.Abs(side) * 2;

            // Зубец стальной, золотая на нём только кромка. Золото на всю
            // высоту — это уже не отделка, а цвет детали: воротник выходил
            // жёлтыми досками за головой.
            mesh.AddBox(new Point3(side * 9.5, top, 14), 7, height, 6,
                        BodyPart.Cape, tint: 1.1 - Math.Abs(side) * 0.04, lean: 6,
                        substance: Substance.Plate);

            // Наклон у кромки свой, соразмерный её высоте. Тот же наклон, что у
            // зубца, разворачивал её почти горизонтально: наклон сдвигает верх
            // формы, и на высоте в три единицы сдвиг в шесть кладёт пластину
            // плашмя. На фигуре это выглядело золотыми пластинками, летящими
            // отдельно от воротника.
            mesh.AddBox(new Point3(side * 9.5, top - height / 2 + 1.5, 15.2), 7.4, 3, 6.4,
                        BodyPart.Cape, tint: 1.3, lean: 0.6, substance: Substance.Gold);
        }

        // ==================== Голова ====================
        //
        // Макушка на -100, подбородок на -80: голова ровно в одну восьмую
        // роста. Череп — труба с кольцами, сверху сужается, у скул шире всего,
        // к подбородку сходит на нет.
        mesh.AddTube(BodyPart.Cape, new[]
        {
            (-101.0, 4.0, 5.0),
            (-98.0, 8.0, 9.5),
            (-94.0, 10.0, 11.5),
            (-88.0, 10.5, 12.0),
            (-82.0, 10.0, 12.0),
            (-76.0, 9.5, 12.5),   // падает на плечи, а не кончается на скулах
        }, tint: 0.95);

        mesh.ShiftLast(0, 0, 1.5);

        // Маска: выступает вперёд из-под капюшона, книзу сужается.
        mesh.AddTube(BodyPart.Head, new[]
        {
            (-95.0, 6.5, 5.5),
            (-91.0, 8.5, 7.5),
            (-86.0, 8.0, 7.0),
            (-82.0, 6.0, 6.0),
            (-79.0, 3.5, 4.0),
        }, tint: 1.06);

        mesh.ShiftLast(0, 0, -3.5);

        // Прорезь для глаз — единственная яркая деталь на лице.
        mesh.AddBox(new Point3(0, -90, -10), 12, 2.6, 3, BodyPart.Head,
                    tint: 1.9, substance: Substance.Glow);

        // Шея: от подбородка до плеч.
        mesh.AddTube(BodyPart.Trim, new[]
        {
            (-81.0, 5.0, 5.0),
            (-72.0, 6.0, 6.0),
        }, tint: 1.06, substance: Substance.Leather);

        // ==================== Корпус ====================
        //
        // Сечение приплюснутое: грудная клетка шире, чем глубже. Талия уже
        // плеч и бёдер — на этом отношении человек и узнаётся.
        mesh.AddTube(BodyPart.Torso, new[]
        {
            (-72.0, 14.0, 9.0),    // основание шеи
            (-66.0, 17.5, 10.5),   // плечевой пояс
            (-60.0, 18.0, 11.0),   // грудь
            (-52.0, 17.0, 10.5),
            (-42.0, 13.0, 9.0),    // талия
            (-32.0, 13.5, 9.5),
            (-24.0, 15.5, 10.5),   // бёдра
            (-18.0, 15.0, 10.0),
        });

        // Грудные пластины поверх корпуса
        mesh.AddBox(new Point3(-8.5, -62, -8), 15, 16, 7, BodyPart.Torso, tint: 1.14, taper: 0.9);
        mesh.AddBox(new Point3(8.5, -62, -8), 15, 16, 7, BodyPart.Torso, tint: 1.14, taper: 0.9);

        // Ядро в груди: обод и свечение.
        mesh.AddBox(new Point3(0, -60, -11), 12, 12, 3, BodyPart.Trim, tint: 1.22);
        mesh.AddBox(new Point3(0, -60, -13), 7, 7, 3, BodyPart.Core, tint: 1.95);

        // ==================== Плечи и руки ====================
        foreach (var side in new[] { -1, 1 })
        {
            // Дельта плеча: округлая шапка, которой раньше не было совсем.
            // Без неё рука выглядела трубой, вставленной в корпус.
            mesh.AddTube(BodyPart.Arms, new[]
            {
                (-71.0, 4.0, 4.5),
                (-68.0, 7.5, 8.0),
                (-64.0, 8.5, 9.0),
                (-59.0, 7.5, 8.0),
            }, tint: 1.0);

            mesh.ShiftLast(side * 22, 0, 0);

            // Наплечник: колпак поверх дельты, наклонённый наружу.
            //
            // Кольца только расширяются книзу и обрываются краем — это и есть
            // колпак. Сначала они шли от узкого верха к широкой середине и
            // снова к узкому низу, то есть описывали сферу, и на плече сидел
            // воздушный шар. Заодно он был просто велик, отчего голова
            // казалась мелкой.
            mesh.AddTube(BodyPart.Arms, new[]
            {
                (-10.0, 3.5, 4.0),
                (-7.0, 7.0, 8.0),
                (-3.0, 9.0, 10.0),
                (2.0, 10.0, 11.0),
                (5.0, 10.5, 11.5),
            }, tint: 1.2);

            mesh.ShiftLast(side * 24, -64, 0);
            mesh.TiltLast(side * 12, side * 24, -64);

            // Золочёная кромка по краю наплечника. Тонкое кольцо поверх
            // колпака: именно кромка и делает пластину кованой вещью, а не
            // куском металла.
            mesh.AddTube(BodyPart.Arms, new[]
            {
                (3.5, 10.2, 11.2),
                (6.5, 10.8, 11.8),
            }, tint: 1.3, substance: Substance.Gold);

            mesh.ShiftLast(side * 24, -64, 0);
            mesh.TiltLast(side * 12, side * 24, -64);

            // Рука: плечо толще предплечья, локоть на уровне талии, запястье
            // на уровне паха. Раньше рука кончалась у пояса и выглядела
            // обрубленной.
            mesh.AddTube(BodyPart.Arms, new[]
            {
                (-62.0, 6.2, 6.2),
                (-52.0, 5.6, 5.6),
                (-45.0, 4.8, 4.8),
                (-42.0, 5.4, 5.4),   // локоть
                (-34.0, 5.0, 5.0),
                (-24.0, 4.2, 4.2),
                (-18.0, 3.8, 3.8),   // запястье
            });

            mesh.ShiftLast(side * 26, 0, 0);
            mesh.TiltLast(side * 3, side * 26, -62);

            // Налокотник: скруглённая шайба на суставе и щиток поверх неё.
            // Коробка торчала углами на округлой руке.
            mesh.AddTube(BodyPart.Arms, new[]
            {
                (-46.0, 5.0, 5.0),
                (-43.0, 6.6, 6.6),
                (-40.0, 6.6, 6.6),
                (-37.0, 5.2, 5.2),
            }, tint: 1.24);

            mesh.ShiftLast(side * 27, 0, 0);

            // Кисть: сжатая ладонь. Тоже новая деталь — раньше рука
            // обрывалась перчаткой-коробкой.
            mesh.AddTube(BodyPart.Arms, new[]
            {
                (-17.0, 3.4, 3.6),
                (-14.0, 4.0, 4.8),
                (-10.0, 3.9, 4.8),
                (-6.0, 2.8, 3.6),
            }, tint: 1.12, substance: Substance.Leather);

            mesh.ShiftLast(side * 28, 0, -1);
        }

        // ==================== Пояс ====================
        mesh.AddBox(new Point3(0, -22, 0), 27, 7, 18, BodyPart.Trim, tint: 1.18);
        mesh.AddBox(new Point3(0, -22, -10), 8, 8, 3.5, BodyPart.Trim, tint: 1.32);   // пряжка

        // Набедренные пластины
        foreach (var side in new[] { -1, 1 })
        {
            mesh.AddBox(new Point3(side * 10, -12, -1), 12, 14, 14, BodyPart.Trim,
                        taper: 0.84, substance: Substance.Leather);
        }

        // ==================== Ноги ====================
        //
        // От паха до пола — половина роста. Колени на +18, щиколотки на +52.
        foreach (var side in new[] { -1, 1 })
        {
            mesh.AddTube(BodyPart.Legs, new[]
            {
                (-16.0, 8.0, 8.0),   // бедро
                (-4.0, 7.4, 7.4),
                (8.0, 6.2, 6.4),
                (16.0, 5.6, 5.8),
                (19.0, 6.4, 6.6),    // колено
                (26.0, 5.6, 5.8),
                (38.0, 4.8, 5.2),
                (50.0, 3.8, 4.4),    // щиколотка
            });

            mesh.ShiftLast(side * 9, 0, 0);

            // Икра: утолщение сзади, а не по кругу. Ровная труба от колена до
            // щиколотки выглядит палкой — голень сужается не сразу.
            mesh.AddTube(BodyPart.Legs, new[]
            {
                (23.0, 4.0, 3.0),
                (28.0, 5.6, 4.6),
                (34.0, 5.2, 4.2),
                (40.0, 3.6, 3.0),
            }, tint: 0.94);

            mesh.ShiftLast(side * 9, 0, 3.5);

            // Наколенник: шайба на суставе, вытянутая вперёд.
            mesh.AddTube(BodyPart.Legs, new[]
            {
                (15.0, 5.2, 5.4),
                (18.0, 6.8, 7.4),
                (21.0, 6.8, 7.4),
                (24.0, 5.4, 5.6),
            }, tint: 1.24);

            mesh.ShiftLast(side * 9, 0, -1.5);

            // Сабатон: скруглённая колодка, вытянутая вперёд. Стопкой коробок
            // он торчал ступеньками из округлой ноги.
            mesh.AddTube(BodyPart.Legs, new[]
            {
                (50.0, 4.0, 5.0),
                (54.0, 5.0, 8.0),
                (58.0, 5.2, 9.5),
                (60.0, 4.6, 9.0),
            }, tint: 1.1);

            mesh.ShiftLast(side * 9, 0, -3);

            // Носок: золочёный, вытянут вперёд.
            mesh.AddTube(BodyPart.Legs, new[]
            {
                (56.0, 4.2, 4.0),
                (59.0, 4.4, 5.0),
                (60.5, 3.4, 4.0),
            }, tint: 1.2, substance: Substance.Gold);

            mesh.ShiftLast(side * 9, 0, -11);
        }

        mesh.Center();
        return mesh;
    }
}
