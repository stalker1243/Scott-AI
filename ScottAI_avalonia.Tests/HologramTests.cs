using System;
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

    [Theory]
    [InlineData(SuitKind.Armor)]
    [InlineData(SuitKind.Cloak)]
    public void Обе_фигуры_собираются(SuitKind kind)
    {
        var mesh = Suits.Build(kind);

        Assert.NotEmpty(mesh.Vertices);
        Assert.NotEmpty(mesh.Faces);

        // Все грани ссылаются на существующие вершины: иначе отрисовка падает
        // с выходом за границы, и вместо фигуры остаётся пустое место.
        Assert.All(mesh.Faces, face =>
            Assert.All(face.Indices, i => Assert.InRange(i, 0, mesh.Vertices.Count - 1)));
    }

    [Fact]
    public void У_плаща_есть_полотнище_а_у_брони_нет()
    {
        var плащ = Suits.Build(SuitKind.Cloak);
        var броня = Suits.Build(SuitKind.Armor);

        Assert.Contains(плащ.Faces, f => f.Part == BodyPart.Cape);
        Assert.DoesNotContain(броня.Faces, f => f.Part == BodyPart.Cape);
    }

    [Theory]
    [InlineData(SuitKind.Armor)]
    [InlineData(SuitKind.Cloak)]
    public void Каждая_подсистема_чем_то_показана(SuitKind kind)
    {
        // Фигура — это показания приборов. Подсистема без своей части просто
        // исчезла бы с экрана, и человек не заметил бы пропажи.
        var mesh = Suits.Build(kind);

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

    [Theory]
    [InlineData(SuitKind.Armor)]
    [InlineData(SuitKind.Cloak)]
    public void Готовые_фигуры_отцентрованы(SuitKind kind)
    {
        // Ровно то, на чём обжигались: фигура вращалась вокруг пояса и уезжала
        // из кадра. Плащ отдельно опасен — он висит за спиной и смещает
        // середину по глубине.
        var mesh = Suits.Build(kind);

        Assert.Equal(0, Середина(mesh, v => v.X), precision: 6);
        Assert.Equal(0, Середина(mesh, v => v.Y), precision: 6);
        Assert.Equal(0, Середина(mesh, v => v.Z), precision: 6);
    }

    private static double Середина(Mesh mesh, Func<Point3, double> ось)
        => (mesh.Vertices.Min(ось) + mesh.Vertices.Max(ось)) / 2;

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
        var mesh = Suits.Build(SuitKind.Armor);
        var грани = Projector.Project(mesh, 0.5, 0.2, 2, 100, 100);

        for (var i = 1; i < грани.Count; i++)
        {
            Assert.True(грани[i].Depth <= грани[i - 1].Depth,
                "грань оказалась дальше предыдущей — порядок нарушен");
        }
    }

    [Fact]
    public void Обращённая_грань_ярче_отвёрнутой()
    {
        var mesh = new Mesh();
        mesh.AddBox(new Point3(0, 0, 0), 20, 20, 20, BodyPart.Torso);

        var грани = Projector.Project(mesh, 0, 0, 1, 0, 0);

        var обращённая = грани.Where(f => f.Facing).Max(f => f.Light);
        Assert.True(обращённая > 0.9, "грань, смотрящая прямо на зрителя, должна светиться в полную силу");
    }

    // ==================== Размещение в кадре ====================

    [Theory]
    [InlineData(SuitKind.Armor)]
    [InlineData(SuitKind.Cloak)]
    public void Фигура_помещается_в_кадр_при_любом_повороте(SuitKind kind)
    {
        // Дважды проваленное требование. Проверяется не формула, а итог: при
        // всех углах поворота ни одна точка не должна оказаться за краями.
        const double width = 240;
        const double height = 400;

        var mesh = Suits.Build(kind);
        var scale = Projector.FitScale(mesh, width, height);

        for (var шаг = 0; шаг < 24; шаг++)
        {
            var yaw = шаг * Math.PI / 12;

            foreach (var pitch in new[] { -0.55, 0.0, 0.55 })
            {
                var грани = Projector.Project(mesh, yaw, pitch, scale, width / 2, height / 2);

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
}
