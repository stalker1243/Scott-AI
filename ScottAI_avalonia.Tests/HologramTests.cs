using System;
using System.Collections.Generic;
using System.Linq;
using ScottAI.Avalonia.Hologram;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Объёмная фигура на главной странице: построение и проекция.
///
/// Своего трёхмерного движка у Avalonia нет, а тащить ради одной фигуры OpenGL
/// значило бы получить вторую цепочку сборки и новый класс поломок на чужих
/// машинах — там и без того хватало «не запускается». Поэтому отрисовщик свой,
/// в сотню строк.
///
/// Своё — значит проверяемое обычными тестами, и это оказалось нужным сразу.
/// Фигура дважды уезжала из кадра: модель строится с головой на отметке минус
/// девяносто и ногами на плюс шестьдесят, а вращение и перспектива считаются
/// вокруг нуля. Середина приходилась ниже пояса, и чем сильнее перспектива, тем
/// дальше фигура выпадала за край.
/// </summary>
public class HologramTests
{
    // ==================== Построение ====================

    [Fact]
    public void Коробка_даёт_восемь_вершин_и_шесть_граней()
    {
        var mesh = new Mesh();
        mesh.AddBox(new Point3(0, 0, 0), 10, 20, 30, BodyPart.Torso);

        Assert.Equal(8, mesh.Vertices.Count);
        Assert.Equal(6, mesh.Faces.Count);
        Assert.All(mesh.Faces, f => Assert.Equal(4, f.Indices.Length));
    }

    [Fact]
    public void Сужение_книзу_делает_из_ящика_торс()
    {
        var mesh = new Mesh();
        mesh.AddBox(new Point3(0, 0, 0), 40, 20, 40, BodyPart.Torso, taper: 0.5);

        var верх = mesh.Vertices.Take(4).Max(v => Math.Abs(v.X));
        var низ = mesh.Vertices.Skip(4).Max(v => Math.Abs(v.X));

        Assert.True(низ < верх, "низ не уже верха — сужение не сработало");
    }

    [Fact]
    public void Фигура_собирается()
    {
        var mesh = Suits.Build();

        Assert.NotEmpty(mesh.Vertices);
        Assert.NotEmpty(mesh.Faces);

        // Все грани ссылаются на существующие вершины: иначе отрисовка падает
        // с выходом за границы, и вместо фигуры остаётся пустое место.
        Assert.All(mesh.Faces, face =>
            Assert.All(face.Indices, i => Assert.InRange(i, 0, mesh.Vertices.Count - 1)));
    }

    [Fact]
    public void У_фигуры_есть_плащ()
    {
        // Плащ — половина силуэта: без него остаётся просто доспех, и фигура
        // теряет то, по чему её узнают.
        Assert.Contains(Suits.Build().Faces, f => f.Part == BodyPart.Cape);
    }

    [Fact]
    public void Каждая_подсистема_чем_то_показана()
    {
        // Фигура — это показания приборов. Подсистема без своей части просто
        // исчезла бы с экрана, и человек не заметил бы пропажи.
        var mesh = Suits.Build();

        foreach (var part in new[] { BodyPart.Head, BodyPart.Core, BodyPart.Torso, BodyPart.Legs })
        {
            Assert.Contains(mesh.Faces, f => f.Part == part);
        }
    }

    // ==================== Центровка ====================

    [Fact]
    public void Центровка_ставит_модель_серединой_в_ноль()
    {
        var mesh = new Mesh();
        mesh.AddBox(new Point3(20, -90, 5), 10, 10, 10, BodyPart.Head);
        mesh.AddBox(new Point3(20, 60, 5), 10, 10, 10, BodyPart.Legs);

        mesh.Center();

        Assert.Equal(0, Середина(mesh, v => v.X), precision: 6);
        Assert.Equal(0, Середина(mesh, v => v.Y), precision: 6);
        Assert.Equal(0, Середина(mesh, v => v.Z), precision: 6);
    }

    [Fact]
    public void Готовая_фигура_отцентрована_по_доспеху()
    {
        // Ровно то, на чём обжигались: фигура вращалась вокруг пояса и уезжала
        // из кадра.
        //
        // Центровка считается по доспеху, а не по всей модели: плащ висит за
        // спиной и свисает ниже пояса, и по нему середина приходится не туда,
        // где человек видит фигуру.
        var mesh = Suits.Build();
        var доспех = ВершиныДоспеха(mesh);

        Assert.Equal(0, Середина(доспех, v => v.X), precision: 6);
        Assert.Equal(0, Середина(доспех, v => v.Y), precision: 6);
        Assert.Equal(0, Середина(доспех, v => v.Z), precision: 6);
    }

    private static List<Point3> ВершиныДоспеха(Mesh mesh)
    {
        var indices = mesh.Faces
            .Where(f => f.Part != BodyPart.Cape)
            .SelectMany(f => f.Indices)
            .Distinct();

        return indices.Select(i => mesh.Vertices[i]).ToList();
    }

    private static double Середина(Mesh mesh, Func<Point3, double> ось)
        => Середина(mesh.Vertices, ось);

    private static double Середина(IReadOnlyCollection<Point3> вершины, Func<Point3, double> ось)
        => (вершины.Min(ось) + вершины.Max(ось)) / 2;

    // ==================== Поворот ====================

    [Fact]
    public void Без_поворота_фигура_смотрит_прямо()
    {
        var mesh = new Mesh();
        mesh.AddBox(new Point3(0, 0, 0), 20, 20, 20, BodyPart.Torso);

        var грани = Projector.Project(mesh, yaw: 0, pitch: 0, scale: 1, centerX: 0, centerY: 0);

        // Передняя и задняя грани есть всегда; к зрителю обращена ровно одна.
        Assert.Contains(грани, f => f.Facing);
        Assert.Contains(грани, f => !f.Facing);
    }

    [Fact]
    public void Поворот_на_полкруга_меняет_видимую_сторону()
    {
        var mesh = new Mesh();
        mesh.AddBox(new Point3(0, 0, 0), 20, 20, 20, BodyPart.Torso);

        var спереди = Projector.Project(mesh, 0, 0, 1, 0, 0);
        var сзади = Projector.Project(mesh, Math.PI, 0, 1, 0, 0);

        // Ближайшая грань спереди и сзади — разные стороны коробки.
        var ближняяСпереди = спереди.Last();
        var ближняяСзади = сзади.Last();

        Assert.NotEqual(
            Math.Round(ближняяСпереди.Points[0].X, 3),
            Math.Round(ближняяСзади.Points[0].X, 3));
    }

    [Fact]
    public void Грани_упорядочены_от_дальних_к_ближним()
    {
        // На этом порядке держится вся отрисовка: рисуя от дальних к ближним,
        // ближние закрывают дальние сами собой. Перепутанный порядок вывернул
        // бы фигуру наизнанку.
        var mesh = Suits.Build();
        var грани = Projector.Project(mesh, 0.5, 0.2, 2, 100, 100);

        for (var i = 1; i < грани.Count; i++)
        {
            Assert.True(грани[i].Depth <= грани[i - 1].Depth,
                "грань оказалась дальше предыдущей — порядок нарушен");
        }
    }

    [Fact]
    public void Свет_падает_сверху()
    {
        // Не придирка к оттенкам: именно разница между верхними и нижними
        // гранями и создаёт объём. Знаки у направления света легко перепутать —
        // экранная ось Y смотрит вниз, — и в первой же версии доспех освещался
        // снизу, отчего выглядел плоским.
        var mesh = new Mesh();
        mesh.AddBox(new Point3(0, 0, 0), 20, 20, 20, BodyPart.Torso);

        var грани = Projector.Project(mesh, 0, 0.5, 1, 0, 0);

        // Верхняя грань коробки выше остальных по экрану.
        var верхняя = грани.OrderBy(f => f.Points.Average(p => p.Y)).First();
        var нижняя = грани.OrderByDescending(f => f.Points.Average(p => p.Y)).First();

        Assert.True(верхняя.Light > нижняя.Light,
            $"верх ({верхняя.Light:0.00}) не светлее низа ({нижняя.Light:0.00})");
    }

    [Fact]
    public void Отвёрнутая_грань_не_рисуется_как_обращённая()
    {
        var mesh = new Mesh();
        mesh.AddBox(new Point3(0, 0, 0), 20, 20, 20, BodyPart.Torso);

        // Угол взят косой намеренно. Если смотреть строго в лоб, боковые грани
        // стоят ребром — их нормаль перпендикулярна взгляду, и отнести их к
        // обращённым или отвёрнутым можно с равным правом. На таком угле
        // проверка ничего бы не значила.
        var грани = Projector.Project(mesh, 0.6, 0.4, 1, 0, 0);

        // У коробки с косого угла видно ровно три грани из шести.
        Assert.Equal(3, грани.Count(f => f.Facing));
    }

    // ==================== Размещение в кадре ====================

    [Fact]
    public void Фигура_помещается_в_кадр_при_любом_повороте()
    {
        // Дважды проваленное требование. Проверяется не формула, а итог: при
        // всех углах поворота ни одна точка не должна оказаться за краями.
        const double width = 240;
        const double height = 400;

        var mesh = Suits.Build();
        var scale = Projector.FitScale(mesh, width, height);
        // Тот же расчёт, что и при отрисовке: считать посадку отдельно значило
        // бы проверять не то, что показывают человеку.
        var centerY = Projector.GroundedCenterY(mesh, scale, height);

        for (var шаг = 0; шаг < 24; шаг++)
        {
            var yaw = шаг * Math.PI / 12;

            foreach (var pitch in new[] { -0.55, 0.0, 0.55 })
            {
                var грани = Projector.Project(mesh, yaw, pitch, scale, width / 2, centerY);

                foreach (var грань in грани)
                {
                    foreach (var (x, y) in грань.Points)
                    {
                        Assert.InRange(x, 0, width);
                        Assert.InRange(y, 0, height);
                    }
                }
            }
        }
    }

    [Fact]
    public void Пустая_модель_не_роняет_подбор_масштаба()
    {
        // Модель может оказаться пустой, если сборку фигуры когда-нибудь
        // сломают. Делить на ноль при этом незачем.
        var scale = Projector.FitScale(new Mesh(), 100, 100);

        Assert.True(scale > 0);
    }

    // ==================== Куда смотрит фигура ====================

    [Fact]
    public void Фигура_повёрнута_лицом_к_зрителю()
    {
        // Перспектива считается как D / (D + z): чем больше Z, тем точка
        // дальше. Значит перёд фигуры — со стороны отрицательного Z.
        //
        // Ровно это и было перепутано: в AddBox стороны коробки были подписаны
        // наоборот, по этим подписям собралась вся модель, и фигура стояла к
        // человеку спиной — вместе с плащом, оттого он и проходил сквозь тело.
        var mesh = Suits.Build();

        var лицо = ВершиныЧасти(mesh, BodyPart.Head);
        var корпус = ВершиныЧасти(mesh, BodyPart.Torso);

        Assert.True(Середина(лицо, v => v.Z) < Середина(корпус, v => v.Z),
                    "маска должна выступать в сторону зрителя, а не от него");

        // Ядро светится на груди, а не между лопаток.
        Assert.True(Середина(ВершиныЧасти(mesh, BodyPart.Core), v => v.Z) < 0);
    }

    [Fact]
    public void Плащ_висит_за_спиной_а_не_сквозь_тело()
    {
        // Замечание с живого просмотра: полотнище проходило сквозь фигуру.
        //
        // Проверяется по соседству: для каждой точки плаща берутся точки
        // доспеха рядом — по высоте и вбок, — и плащ обязан быть за ними,
        // то есть глубже. Сравнивать одни только крайние значения бесполезно:
        // плащ шире фигуры и ниже её, и общие границы пересечения не покажут.
        var mesh = Suits.Build();

        var доспех = ВершиныЧасти(mesh, BodyPart.Torso)
            .Concat(ВершиныЧасти(mesh, BodyPart.Arms))
            .Concat(ВершиныЧасти(mesh, BodyPart.Head))
            .Concat(ВершиныЧасти(mesh, BodyPart.Core))
            .ToList();

        foreach (var точка in Полотнище(mesh))
        {
            var рядом = доспех
                .Where(v => Math.Abs(v.Y - точка.Y) < 7 && Math.Abs(v.X - точка.X) < 7)
                .ToList();

            if (рядом.Count == 0) continue;

            var глубжеВсех = рядом.Max(v => v.Z);

            Assert.True(точка.Z >= глубжеВсех,
                        $"плащ вошёл в доспех на высоте {точка.Y:F0}: " +
                        $"ткань на глубине {точка.Z:F1}, металл на {глубжеВсех:F1}");
        }
    }

    /// <summary>
    /// Само полотнище плаща — без капюшона и воротника.
    ///
    /// Они тоже помечены как Cape (красятся тканью), но капюшон облегает
    /// голову, и по нему любая проверка на пересечение с доспехом сработает
    /// впустую. Полотнище строится первым, и это его вершины идут в начале.
    /// </summary>
    private static List<Point3> Полотнище(Mesh mesh)
    {
        var сетка = new Mesh();
        сетка.AddCape(top: 0, height: 1, halfWidth: 1, depth: 1);

        return mesh.Vertices.Take(сетка.Vertices.Count).ToList();
    }

    private static List<Point3> ВершиныЧасти(Mesh mesh, BodyPart часть)
    {
        var indices = mesh.Faces
            .Where(f => f.Part == часть)
            .SelectMany(f => f.Indices)
            .Distinct();

        return indices.Select(i => mesh.Vertices[i]).ToList();
    }

    [Fact]
    public void Плащ_виден_с_обеих_сторон()
    {
        // Отрисовщик пропускает грани, отвёрнутые от зрителя. Для замкнутых
        // форм это верно, но у ткани нет толщины, и полотнище просто исчезало:
        // спереди плаща не было видно вообще, только воротник.
        var mesh = Suits.Build();

        foreach (var yaw in new[] { 0.0, Math.PI })
        {
            var ткань = Projector
                .Project(mesh, yaw, 0, 1, 0, 0)
                .Where(f => f.Part == BodyPart.Cape && f.Facing)
                .ToList();

            Assert.True(ткань.Count > 20,
                        $"при повороте {yaw:F2} видно всего {ткань.Count} кусков ткани");
        }
    }

    // ==================== Округлость ====================

    [Fact]
    public void Труба_натягивается_на_кольца_сечений()
    {
        var mesh = new Mesh();
        mesh.AddTube(BodyPart.Torso, new[]
        {
            (0.0, 10.0, 6.0),
            (20.0, 4.0, 4.0),
        }, sides: 8);

        // Восемь точек на кольцо, два кольца.
        Assert.Equal(16, mesh.Vertices.Count);

        // Восемь боковых граней плюс две крышки: без крышек труба
        // просвечивает насквозь, и внутри видны её же задние грани.
        Assert.Equal(10, mesh.Faces.Count);

        // Сечение приплюснутое: поперёк шире, чем в глубину.
        var верх = mesh.Vertices.Take(8).ToList();
        Assert.True(верх.Max(v => v.X) > верх.Max(v => v.Z));
    }

    [Fact]
    public void Одного_кольца_мало_для_трубы()
    {
        var mesh = new Mesh();
        mesh.AddTube(BodyPart.Torso, new[] { (0.0, 10.0, 10.0) });

        Assert.Empty(mesh.Faces);
    }

    [Fact]
    public void Корпус_и_конечности_не_квадратные()
    {
        // Замечание с живого просмотра: фигура выглядела набором ящиков.
        //
        // У коробки всего шесть направлений граней, и сколько коробок ни
        // ставь рядом, больше их не станет. Округлая форма узнаётся именно по
        // числу разных направлений.
        var mesh = Suits.Build();

        foreach (var часть in new[] { BodyPart.Torso, BodyPart.Arms, BodyPart.Legs })
        {
            Assert.True(НаправленийГраней(mesh, часть) > 6,
                        $"{часть}: направлений всего {НаправленийГраней(mesh, часть)}, " +
                        "форма собрана коробками");
        }
    }

    private static int НаправленийГраней(Mesh mesh, BodyPart часть)
    {
        var направления = new HashSet<(int, int, int)>();

        foreach (var грань in mesh.Faces.Where(f => f.Part == часть))
        {
            var a = mesh.Vertices[грань.Indices[0]];
            var b = mesh.Vertices[грань.Indices[1]];
            var c = mesh.Vertices[грань.Indices[2]];

            var n = (b - a).Cross(c - a);
            if (n.Length < 0.0001) continue;

            направления.Add(((int)Math.Round(n.X / n.Length * 10),
                             (int)Math.Round(n.Y / n.Length * 10),
                             (int)Math.Round(n.Z / n.Length * 10)));
        }

        return направления.Count;
    }
}
