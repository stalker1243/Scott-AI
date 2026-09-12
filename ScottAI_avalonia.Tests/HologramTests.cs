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
        var mesh = Figure.Build();

        Assert.NotEmpty(mesh.Vertices);
        Assert.NotEmpty(mesh.Faces);

        // Все грани ссылаются на существующие вершины: иначе отрисовка падает
        // с выходом за границы, и вместо фигуры остаётся пустое место.
        Assert.All(mesh.Faces, face =>
            Assert.All(face.Indices, i => Assert.InRange(i, 0, mesh.Vertices.Count - 1)));
    }

    [Fact]
    public void Каждая_подсистема_чем_то_показана()
    {
        // Фигура — это показания приборов. Подсистема без своей части просто
        // исчезла бы с экрана, и человек не заметил бы пропажи.
        var mesh = Figure.Build();

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
        var mesh = Figure.Build();
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

        var mesh = Figure.Build();
        var scale = Projector.FitScale(mesh, width, height);

        for (var шаг = 0; шаг < 24; шаг++)
        {
            var yaw = шаг * Math.PI / 12;

            foreach (var pitch in new[] { -Projector.MaxPitch, 0.0, Projector.MaxPitch })
            {
                // Тот же расчёт, что и при отрисовке, вместе с наклоном:
                // считать посадку отдельно значило бы проверять не то, что
                // показывают человеку.
                var centerY = Projector.GroundedCenterY(mesh, scale, height, pitch);
                var грани = Projector.Project(mesh, yaw, pitch, scale, width / 2, centerY);

                foreach (var грань in грани)
                {
                    foreach (var (x, y) in грань.Points)
                    {
                        // Сообщение важнее самой проверки: без него видно
                        // только «значение вне диапазона», и непонятно, какой
                        // угол и какая часть фигуры вылезли за край.
                        Assert.True(x >= 0 && x <= width && y >= 0 && y <= height,
                            $"поворот {yaw:F2}, наклон {pitch:F2}, {грань.Part}: " +
                            $"точка ({x:F1}, {y:F1}) вне кадра {width}×{height}");
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
        var mesh = Figure.Build();

        // Свечение в груди, а не между лопаток.
        Assert.True(Середина(ВершиныЧасти(mesh, BodyPart.Core), v => v.Z) < 0);

        // Стопы вытянуты вперёд, как у человека, а не назад.
        var ступни = ВершиныЧасти(mesh, BodyPart.Legs);
        var самаяНижняя = ступни.Max(v => v.Y);
        var носок = ступни.Where(v => v.Y > самаяНижняя - 12).Min(v => v.Z);

        Assert.True(носок < -6, $"стопы смотрят не вперёд: носок на глубине {носок:F1}");
    }

    private static List<Point3> ВершиныЧасти(Mesh mesh, BodyPart часть)
    {
        var indices = mesh.Faces
            .Where(f => f.Part == часть)
            .SelectMany(f => f.Indices)
            .Distinct();

        return indices.Select(i => mesh.Vertices[i]).ToList();
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
        var mesh = Figure.Build();

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

    [Fact]
    public void Модель_остаётся_по_карману()
    {
        // Каждая грань на каждом кадре сортируется по глубине и рисуется
        // дважды — заливкой и обводкой. Отрисовщик здесь свой, программный, и
        // видеокарта ему не помогает: число граней прямо превращается в
        // кадры в секунду.
        //
        // Предел не круглое число, а запас над нынешним размером: он должен
        // мешать модели разрастаться незаметно, а не запрещать детали.
        var mesh = Figure.Build();

        Assert.True(mesh.Faces.Count < 1400,
                    $"граней {mesh.Faces.Count}, вершин {mesh.Vertices.Count}");
    }

    [Fact]
    public void Рука_не_ломается_вбок()
    {
        // Замечание с живого просмотра: «руки не на своём месте, как будто
        // парят над воздухом».
        //
        // Так и было. Предплечье строилось на оси, сдвигалось вбок и
        // наклонялось внутрь — отчего его нижний конец уезжал к телу на три
        // единицы, — а кисть строилась после и ставилась на своё, ни с чем не
        // согласованное место.
        //
        // Проверяются оси самих форм, а не поперечные слои фигуры. Слои для
        // этого не годятся: предплечье кончается и ладонь начинается на одной
        // высоте, в срез попадают обе, и середина среза выходит где-то между
        // ними — излом размазывается ровно там, где его надо увидеть.
        var mesh = Figure.Build();

        var руки = mesh.Shapes
            .Where(s => s.Part == BodyPart.Arms)
            .Select(s => new
            {
                Центр = Enumerable.Range(s.Start, s.Count).Average(i => mesh.Vertices[i].X),
                Верх = Enumerable.Range(s.Start, s.Count).Min(i => mesh.Vertices[i].Y),
            })
            .Where(s => s.Центр > 0)      // одной стороны довольно: они зеркальны
            .OrderBy(s => s.Верх)
            .ToList();

        Assert.True(руки.Count >= 4, "рука должна быть собрана из нескольких форм");

        for (var i = 1; i < руки.Count; i++)
        {
            var сдвиг = Math.Abs(руки[i].Центр - руки[i - 1].Центр);

            Assert.True(сдвиг < 2.5,
                        $"ось руки прыгает на высоте {руки[i].Верх:F0}: " +
                        $"с {руки[i - 1].Центр:F1} на {руки[i].Центр:F1}");
        }
    }

    [Fact]
    public void Кадр_успевает_посчитаться()
    {
        // Пальцы, плотные сечения и мелкие детали обошлись в тысячу с лишним
        // граней вместо прежних четырёхсот. Детали того стоят, но у них есть
        // цена, и она должна быть видна здесь, а не на чужой слабой машине.
        //
        // Шестнадцать миллисекунд — весь бюджет кадра при шестидесяти в
        // секунду, и расчёт проекции обязан занимать малую его часть: дальше
        // ещё сортировка и собственно отрисовка.
        var mesh = Figure.Build();

        // Прогрев: первый вызов платит за подготовку, и мерить его нечестно.
        Projector.Project(mesh, 0, 0, 2, 100, 200);

        var часы = System.Diagnostics.Stopwatch.StartNew();
        const int кадров = 60;

        for (var i = 0; i < кадров; i++)
        {
            Projector.Project(mesh, i * 0.1, 0.2, 2, 100, 200);
        }

        часы.Stop();
        var наКадр = часы.Elapsed.TotalMilliseconds / кадров;

        Assert.True(наКадр < 4, $"расчёт кадра занимает {наКадр:F2} мс");
    }

    // ==================== Материалы и цвет ====================

    [Fact]
    public void Блик_попадает_на_грани_восьмигранника()
    {
        // Ровно то, на чём обожглись: при резкости 28 блик сходился в точку
        // между гранями и не попадал ни на одну. На фигуре его не было видно
        // вовсе, хотя считался он правильно.
        //
        // Грани восьмигранного сечения стоят через сорок пять градусов, и блик
        // должен быть шире этого зазора.
        var mesh = new Mesh();
        mesh.AddTube(BodyPart.Torso, new[]
        {
            (-20.0, 12.0, 12.0),
            (20.0, 12.0, 12.0),
        });

        var (сила, резкость) = Palette.Gloss(Substance.Body);

        var самыйЯркий = Projector
            .Project(mesh, 0, 0, 1, 0, 0)
            .Where(f => f.Facing)
            .Max(f => Math.Pow(f.Mirror, резкость) * сила);

        Assert.True(самыйЯркий > 0.08,
                    $"самый яркий блик на трубе — всего {самыйЯркий:F3}, его не видно");
    }

    [Fact]
    public void Блик_гаснет_на_отвёрнутой_грани()
    {
        // Низ коробки отвёрнут и от зрителя, и от источника: отражать ему
        // нечего.
        var mesh = new Mesh();
        mesh.AddBox(new Point3(0, 0, 0), 20, 20, 20, BodyPart.Torso);

        var грани = Projector.Project(mesh, 0, 0, 1, 0, 0).ToList();

        var кЗрителю = грани.Where(f => f.Facing).Max(f => f.Mirror);
        var отЗрителя = грани.Where(f => !f.Facing).Max(f => f.Mirror);

        Assert.True(кЗрителю > отЗрителя,
                    "обращённая грань должна отражать сильнее отвёрнутой");
    }

}
