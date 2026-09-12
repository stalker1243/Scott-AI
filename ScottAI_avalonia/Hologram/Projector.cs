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

            // Освещённость считается по нормали: грань, смотрящая на зрителя,
            // ярче той, что стоит ребром.
            var length = normal.Length;
            var light = length > 0.0001 ? Math.Clamp(-normal.Z / length, 0, 1) : 0;

            result.Add(new ProjectedFace
            {
                Points = points,
                Depth = depth,
                Part = face.Part,
                Light = 0.45 + 0.55 * light,
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
    /// <summary>Половина высоты модели — по ней фигуру ставят ногами на кольца.</summary>
    public static double HalfHeight(Mesh mesh)
        => mesh.Vertices.Count == 0 ? 0 : mesh.Vertices.Max(v => Math.Abs(v.Y));

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
    /// </summary>
    public static double GroundedCenterY(Mesh mesh, double scale, double height)
    {
        if (mesh.Vertices.Count == 0) return height / 2;

        var half = HalfHeight(mesh);
        if (half <= 0) return height / 2;

        // Увеличение считается по самым нижним точкам, а не по всей модели.
        //
        // Фигура стоит на ступнях, а они близко к оси вращения: перспектива
        // растягивает их куда слабее, чем разведённые плечи. Взяв общее
        // увеличение, фигуру приходилось поднимать с запасом — и она повисала
        // над кольцами проекции вместо того, чтобы стоять в них.
        var lowest = mesh.Vertices.Where(v => v.Y > half * 0.8).ToList();
        var footReach = lowest.Count > 0
            ? lowest.Max(v => Math.Sqrt(v.X * v.X + v.Z * v.Z))
            : Reach(mesh);

        var closeUp = ViewerDistance / Math.Max(1, ViewerDistance - footReach);

        return height - half * scale * closeUp;
    }

    public static double FitScale(Mesh mesh, double width, double height, double margin = 0.94)
    {
        if (mesh.Vertices.Count == 0) return 1;

        var maxY = HalfHeight(mesh);
        var reach = Reach(mesh);
        var closeUp = CloseUp(mesh);

        var byWidth = reach > 0 ? width / 2 / (reach * closeUp) : 1;
        var byHeight = maxY > 0 ? height / 2 / (maxY * closeUp) : 1;

        return Math.Min(byWidth, byHeight) * margin;
    }
}
