using System;
using System.Collections.Generic;
using System.Linq;

namespace ScottAI.Avalonia.Hologram;

/// <summary>Грань, уже приведённая к экрану: куда рисовать и в каком порядке.</summary>
public sealed class ProjectedFace
{
    public required (double X, double Y)[] Points { get; init; }

    /// <summary>Глубина середины грани. По ней грани и упорядочиваются.</summary>
    public required double Depth { get; init; }

    /// <summary>Какую подсистему показывает.</summary>
    public required BodyPart Part { get; init; }

    /// <summary>
    /// Насколько грань освещена: от нуля (отвёрнута) до единицы (смотрит прямо).
    ///
    /// Настоящего света здесь нет, и не нужно: голограмма светится сама. Но без
    /// разницы в яркости между сторонами фигура при повороте превращается в
    /// плоское пятно.
    /// </summary>
    public required double Light { get; init; }

    /// <summary>Обращена ли грань к зрителю.</summary>
    public required bool Facing { get; init; }

    /// <summary>Собственная яркость детали, заданная при построении модели.</summary>
    public double Tint { get; init; } = 1.0;

    /// <summary>
    /// Насколько ровно грань отражает источник в сторону зрителя.
    ///
    /// Ноль — отражение уходит мимо, единица — попадает прямо в глаз. Сама по
    /// себе величина ничего не говорит о материале: во что её превратить,
    /// решает палитра, у сукна блика не будет и при единице.
    /// </summary>
    public required double Mirror { get; init; }

    /// <summary>Из чего грань сделана.</summary>
    public required Substance Substance { get; init; }
}

/// <summary>
/// Превращение объёмной модели в то, что можно нарисовать.
///
/// Здесь всё, что отвечает за «крутится»: поворот вокруг своей оси, наклон,
/// перспектива и порядок отрисовки. Своего трёхмерного движка у Avalonia нет,
/// а тащить ради одной фигуры целый OpenGL — значит получить вторую цепочку
/// сборки и новый класс поломок на чужих машинах. Простой отрисовщик в сотню
/// строк делает ровно то, что нужно, и проверяется обычными тестами.
/// </summary>
public static class Projector
{
    /// <summary>
    /// Расстояние до зрителя в единицах модели.
    ///
    /// Чем меньше, тем сильнее перспектива. Двести пятьдесят — фигура выглядит
    /// объёмной, но ещё не искажается как через дверной глазок.
    /// </summary>
    public const double ViewerDistance = 250;

    // Направление света: сверху, слева и спереди. Нормализовано вручную —
    // считать длину на каждой грани незачем, вектор не меняется.
    //
    // Знаки выверены, а не подобраны: экранная ось Y смотрит вниз, поэтому
    // верхняя грань имеет нормаль (0, -1, 0). Освещённость считается как
    // -(n · L), и чтобы верх был светлее низа, составляющая Y у света должна
    // быть положительной. Сначала все три знака стояли наоборот, и доспех
    // освещался снизу — проверка «обращённая грань ярче отвёрнутой» это и
    // показала.
    private const double LightX = 0.45;
    private const double LightY = 0.72;
    private const double LightZ = 0.53;

    // Половинный вектор между направлением к источнику и направлением к
    // зрителю — normalize(-L + (0, 0, -1)). Посчитан один раз: свет не
    // движется, и пересчитывать его на каждой грани каждого кадра незачем.
    private const double HalfLength = 1.7498;
    private const double HalfX = -LightX / HalfLength;
    private const double HalfY = -LightY / HalfLength;
    private const double HalfZ = (-LightZ - 1) / HalfLength;

    /// <summary>Сколько света достаётся грани, отвёрнутой от источника.</summary>
    private const double Ambient = 0.34;

    /// <summary>Вклад наклонного света — им и создаётся объём.</summary>
    private const double Diffuse = 0.62;

    /// <summary>Слабая подсветка со стороны зрителя.</summary>
    private const double Rim = 0.16;

    /// <summary>
    /// Разложить модель по граням, готовым к отрисовке.
    ///
    /// Грани возвращаются упорядоченными от дальних к ближним: рисуя в этом
    /// порядке, ближние закрывают дальние сами собой. Это старый приём
    /// художника, и для выпуклой фигуры из коробок его достаточно — буфер
    /// глубины здесь был бы стрельбой из пушки по воробьям.
    /// </summary>
    public static List<ProjectedFace> Project(
        Mesh mesh, double yaw, double pitch, double scale,
        double centerX, double centerY)
    {
        var rotated = new Point3[mesh.Vertices.Count];

        var cosYaw = Math.Cos(yaw);
        var sinYaw = Math.Sin(yaw);
        var cosPitch = Math.Cos(pitch);
        var sinPitch = Math.Sin(pitch);

        for (var i = 0; i < mesh.Vertices.Count; i++)
        {
            var v = mesh.Vertices[i];

            // Вокруг вертикальной оси — это и есть «покрутить фигуру».
            var x = v.X * cosYaw + v.Z * sinYaw;
            var z = -v.X * sinYaw + v.Z * cosYaw;

            // Наклон: смотреть чуть сверху или чуть снизу.
            var y = v.Y * cosPitch - z * sinPitch;
            z = v.Y * sinPitch + z * cosPitch;

            rotated[i] = new Point3(x, y, z);
        }

        var result = new List<ProjectedFace>(mesh.Faces.Count);

        foreach (var face in mesh.Faces)
        {
            var points = new (double X, double Y)[face.Indices.Length];
            var depth = 0.0;

            for (var i = 0; i < face.Indices.Length; i++)
            {
                var p = rotated[face.Indices[i]];
                var perspective = ViewerDistance / (ViewerDistance + p.Z);

                points[i] = (centerX + p.X * perspective * scale,
                             centerY + p.Y * perspective * scale);
                depth += p.Z;
            }

            depth /= face.Indices.Length;

            var normal = Normal(rotated, face.Indices);
            var facing = normal.Z <= 0;

            // Освещённость: источник светит сверху, слева и спереди.
            //
            // Раньше яркость считалась просто по тому, насколько грань
            // повёрнута к зрителю. Выходило плоско: все обращённые к человеку
            // пластины светились одинаково, и металл выглядел бумагой. С
            // наклонным светом у доспеха появляются светлые верхние грани и
            // тёмные нижние — то, по чему объём и узнают.
            var length = normal.Length;
            var lambert = 0.0;
            var mirror = 0.0;

            if (length > 0.0001)
            {
                var nx = normal.X / length;
                var ny = normal.Y / length;
                var nz = normal.Z / length;

                lambert = Math.Clamp(
                    -(nx * LightX + ny * LightY + nz * LightZ), 0, 1);

                // Блик по половинному вектору: если нормаль смотрит ровно
                // между источником и зрителем, отражение попадает в глаз.
                //
                // Вектор к источнику — это минус направление света, вектор к
                // зрителю — минус ось глубины: экран ближе к зрителю там, где
                // Z меньше.
                mirror = Math.Clamp(
                    nx * HalfX + ny * HalfY + nz * HalfZ, 0, 1);
            }

            // Подсветка со стороны зрителя, слабая: она не даёт теневым
            // граням проваливаться в чёрноту, а голограмма светится сама.
            var toViewer = length > 0.0001 ? Math.Clamp(-normal.Z / length, 0, 1) : 0;

            result.Add(new ProjectedFace
            {
                Points = points,
                Depth = depth,
                Part = face.Part,
                Tint = face.Tint,
                Substance = face.Substance,
                Light = Ambient + Diffuse * lambert + Rim * toViewer,
                Mirror = mirror,
                Facing = facing,
            });
        }

        // От дальних к ближним.
        result.Sort((a, b) => b.Depth.CompareTo(a.Depth));
        return result;
    }

    /// <summary>Нормаль грани — по двум её первым рёбрам.</summary>
    private static Point3 Normal(Point3[] vertices, int[] indices)
    {
        if (indices.Length < 3) return new Point3(0, 0, 0);

        var a = vertices[indices[0]];
        var b = vertices[indices[1]];
        var c = vertices[indices[2]];

        return (b - a).Cross(c - a);
    }

    /// <summary>
    /// Подобрать масштаб так, чтобы фигура целиком помещалась в отведённое место.
    ///
    /// Считается по самой модели, а не подбирается на глаз: у плаща и брони
    /// разные размеры, и зашитое число обрезало бы одну из фигур.
    /// </summary>
    /// <summary>
    /// Насколько сильно фигуру разрешено наклонять.
    ///
    /// То же число, что и предел наклона мышью в самом холсте. Оно нужно при
    /// подборе масштаба: наклонённая фигура занимает по высоте больше, чем её
    /// рост, и не знать об этом подбор не имеет права.
    /// </summary>
    public const double MaxPitch = 0.55;

    /// <summary>
    /// Половина высоты модели — по ней фигуру ставят ногами на кольца.
    ///
    /// При наклоне вертикальный размер проекции складывается из двух частей:
    /// рост, сжатый косинусом наклона, и глубина, развёрнутая синусом. Вторая
    /// часть долго отсутствовала в расчёте, и при наклоне ступни вылезали за
    /// нижний край кадра — на невысокой фигуре в доспехе это пряталось в запас
    /// в шесть процентов, на фигуре человеческих пропорций запас кончился.
    ///
    /// Глубина берётся как отход от оси вращения: при повороте вокруг неё
    /// точка уезжает в глубину ровно на это расстояние, не дальше.
    /// </summary>
    public static double HalfHeight(Mesh mesh, double pitch = 0)
    {
        if (mesh.Vertices.Count == 0) return 0;

        var tall = mesh.Vertices.Max(v => Math.Abs(v.Y));
        if (pitch == 0) return tall;

        return tall * Math.Cos(pitch) + Reach(mesh) * Math.Sin(Math.Abs(pitch));
    }

    /// <summary>
    /// Насколько далеко точки отходят от оси вращения.
    ///
    /// Берётся расстояние в плоскости пола: при любом повороте дальше него
    /// точка не уедет.
    /// </summary>
    public static double Reach(Mesh mesh)
        => mesh.Vertices.Count == 0
            ? 0
            : mesh.Vertices.Max(v => Math.Sqrt(v.X * v.X + v.Z * v.Z));

    /// <summary>
    /// Во сколько раз перспектива увеличивает ближнюю к зрителю половину.
    ///
    /// Нужна дважды: при подборе масштаба и при посадке фигуры. Считать её в
    /// двух местах по отдельности — верный способ развести их между собой.
    /// </summary>
    public static double CloseUp(Mesh mesh)
        => ViewerDistance / Math.Max(1, ViewerDistance - Reach(mesh));

    /// <summary>
    /// Где должна быть середина фигуры, чтобы она стояла ногами на низу.
    ///
    /// Просто «высота минус половина роста» не годится: перспектива увеличивает
    /// то, что ближе к зрителю, и повёрнутая к человеку ступня опускается ниже
    /// плоского расчёта. Проверка это и поймала — фигура вылезала за нижний
    /// край ровно тем боком, который к зрителю.
    ///
    /// Второй раз та же проверка поймала наклон: при нём ступни уходили за
    /// край ещё на две десятых пикселя. Поэтому для каждой вершины считается,
    /// как низко она может оказаться при любом повороте — рост, сжатый
    /// косинусом наклона, плюс отход от оси, развёрнутый синусом, и всё это
    /// увеличенное перспективой в самом близком к зрителю положении.
    ///
    /// Оценка берётся по худшему повороту, а не по текущему: иначе фигура
    /// подпрыгивала бы, вращаясь. При нулевом наклоне она точная — это обычное
    /// состояние фигуры, и повисать над кольцами она не должна.
    /// </summary>
    public static double GroundedCenterY(Mesh mesh, double scale, double height, double pitch = 0)
    {
        if (mesh.Vertices.Count == 0) return height / 2;

        var cos = Math.Cos(pitch);
        var sin = Math.Abs(Math.Sin(pitch));
        var drop = 0.0;

        foreach (var v in mesh.Vertices)
        {
            var reach = Math.Sqrt(v.X * v.X + v.Z * v.Z);

            var low = v.Y * cos + reach * sin;
            if (low <= 0) continue;

            // Насколько близко точка может подойти к зрителю. Наклон сам по
            // себе подтаскивает низ фигуры вперёд — при взгляде снизу ступни
            // оказываются ближе плеч, — и без этого слагаемого перспектива
            // недооценивалась в полтора раза, а ступни уходили за нижний край.
            var nearest = v.Y * Math.Sin(pitch) - reach * Math.Abs(cos);
            var closeUp = ViewerDistance / Math.Max(1, ViewerDistance + nearest);

            drop = Math.Max(drop, low * closeUp);
        }

        if (drop <= 0) return height / 2;

        return height - drop * scale;
    }

    public static double FitScale(Mesh mesh, double width, double height, double margin = 0.94)
    {
        if (mesh.Vertices.Count == 0) return 1;

        // Высота считается для самого сильного наклона, какой человек может
        // задать мышью: масштаб подбирается один раз, а наклон меняется на
        // ходу, и пересчитывать его на каждом кадре значило бы дёргать размер
        // фигуры под рукой.
        var maxY = HalfHeight(mesh, MaxPitch);
        var reach = Reach(mesh);
        var closeUp = CloseUp(mesh);

        var byWidth = reach > 0 ? width / 2 / (reach * closeUp) : 1;
        var byHeight = maxY > 0 ? height / 2 / (maxY * closeUp) : 1;

        return Math.Min(byWidth, byHeight) * margin;
    }
}
