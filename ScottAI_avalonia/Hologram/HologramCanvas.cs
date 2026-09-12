using System;
using System.Globalization;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using ScottAI.Avalonia.Converters;

namespace ScottAI.Avalonia.Hologram;

/// <summary>
/// Фигура, показывающая состояние машины.
///
/// Каждая часть отвечает за свою подсистему: голова — видеокарта, корпус —
/// оперативная память, руки и свечение в груди — процессор, ноги — диск. Цвет
/// меняется от бирюзового через янтарный к красному, так что состояние
/// читается одним взглядом. Рядом с каждой частью выноска с числом — для
/// случаев, когда цвета мало.
///
/// ПОЧЕМУ ПЛОСКО. Здесь была объёмная фигура со своим программным
/// отрисовщиком: сортировка граней по глубине, перспектива, освещение,
/// вращение мышью. Она работала, но форму задавали кольца сечений, то есть
/// окружности, — а у живого тела нет ни одного круглого сечения. Чем ближе к
/// человеку, тем больше граней требовалось, и к тысяче с лишним фасетки всё
/// равно были видны.
///
/// Плоский силуэт рисуется кривыми, у которых нет ни граней, ни колец, — форма
/// получается точнее. Заодно исчезли сортировка, перспектива и тысяча
/// геометрий на кадр: теперь это десяток путей.
/// </summary>
public class HologramCanvas : Control
{
    // ==================== Что показываем ====================

    public static readonly StyledProperty<double> GpuProperty =
        AvaloniaProperty.Register<HologramCanvas, double>(nameof(Gpu));

    public static readonly StyledProperty<double> CpuProperty =
        AvaloniaProperty.Register<HologramCanvas, double>(nameof(Cpu));

    public static readonly StyledProperty<double> RamProperty =
        AvaloniaProperty.Register<HologramCanvas, double>(nameof(Ram));

    public static readonly StyledProperty<double> DiskProperty =
        AvaloniaProperty.Register<HologramCanvas, double>(nameof(Disk));

    /// <summary>Сколько процессов запущено — пояснение под числом процессора.</summary>
    public static readonly StyledProperty<int> ProcessesProperty =
        AvaloniaProperty.Register<HologramCanvas, int>(nameof(Processes));

    /// <summary>
    /// Сколько места занято на диске.
    ///
    /// Стоит рядом с нагрузкой намеренно: именно смешение этих двух величин
    /// однажды заставило лаунчер показывать восемьдесят процентов на диске,
    /// который ничего не делал.
    /// </summary>
    public static readonly StyledProperty<double> DiskUsageProperty =
        AvaloniaProperty.Register<HologramCanvas, double>(nameof(DiskUsage));

    public double Gpu { get => GetValue(GpuProperty); set => SetValue(GpuProperty, value); }
    public double Cpu { get => GetValue(CpuProperty); set => SetValue(CpuProperty, value); }
    public double Ram { get => GetValue(RamProperty); set => SetValue(RamProperty, value); }
    public double Disk { get => GetValue(DiskProperty); set => SetValue(DiskProperty, value); }
    public int Processes { get => GetValue(ProcessesProperty); set => SetValue(ProcessesProperty, value); }
    public double DiskUsage { get => GetValue(DiskUsageProperty); set => SetValue(DiskUsageProperty, value); }

    static HologramCanvas()
    {
        AffectsRender<HologramCanvas>(GpuProperty, CpuProperty, RamProperty, DiskProperty,
                                      ProcessesProperty, DiskUsageProperty);
    }

    /// <summary>Отступ под кольца проекции внизу.</summary>
    private const double Pedestal = 26;

    /// <summary>Сколько места оставить по бокам под выноски.</summary>
    /// <summary>
    /// Наименьшее поле по бокам — на случай, если подписей вдруг не будет.
    /// </summary>
    private const double MinSideRoom = 70;

    /// <summary>Кегль названия подсистемы, числа и пояснения.</summary>
    private const double CaptionSize = 9;
    private const double ReadingSize = 15;

    public HologramCanvas()
    {
        ClipToBounds = true;
    }

    public override void Render(DrawingContext context)
    {
        var width = Bounds.Width;
        var height = Bounds.Height;
        if (width <= 0 || height <= 0) return;

        // Масштаб подбирается по месту, а не задаётся числом: фигура описана в
        // собственной сетке ростом в двести единиц и должна одинаково верно
        // смотреться при любом размере окна.
        // Поле под выноски берётся по самой длинной подписи, а не по доле
        // ширины. Доля то вмещала текст, то нет: от «ВИДЕОКАРТА» оставалось
        // «ИДЕОКАРТА». Ширину текста можно измерить — гадать о ней незачем.
        var readings = Readings();
        var sideRoom = Math.Max(MinSideRoom, LongestReading(readings) + 18);

        var scale = Math.Min(
            (width - sideRoom * 2) / (Silhouette.HalfWidth * 2),
            (height - Pedestal) / Silhouette.Height);

        if (scale <= 0) return;

        var originX = width / 2;

        // Фигура прижимается к низу, а не центрируется по высоте: под ней
        // кольца проекции, и стоять она должна в них. Центрированная висела
        // над кольцами, и это было первым, что бросалось в глаза.
        var originY = height - Pedestal - Silhouette.Height * scale;

        DrawFigure(context, originX, originY, scale);
        DrawCore(context, originX, originY, scale);
        DrawPointers(context, originX, originY, scale, width, sideRoom, readings);
    }

    private Point Place(double originX, double originY, double scale, Point p)
        => new(originX + p.X * scale, originY + p.Y * scale);

    /// <summary>Одна выноска: что показываем и чем поясняем.</summary>
    private readonly record struct Reading(
        BodyPart Part, string Name, double Value, int Side, string Note);

    /// <summary>
    /// Что показывают выноски.
    ///
    /// Пояснение объясняет выбор части: почему видеокарта — это голова, а ноги
    /// — диск. Под диском стоит заполненность: именно смешение её с нагрузкой
    /// однажды и сбило с толку, когда лаунчер показывал восемьдесят процентов
    /// на диске, который ничего не делал.
    /// </summary>
    private Reading[] Readings() => new[]
    {
        new Reading(BodyPart.Head, "ВИДЕОКАРТА", Gpu, -1, "голова"),
        new Reading(BodyPart.Torso, "ПАМЯТЬ", Ram, 1, "корпус"),
        new Reading(BodyPart.Arms, "ПРОЦЕССОР", Cpu, -1, $"{Processes} процессов"),
        new Reading(BodyPart.Legs, "ДИСК", Disk, 1, $"занято {DiskUsage:0}%"),
    };

    /// <summary>Ширина самой длинной подписи в точках.</summary>
    private double LongestReading(Reading[] readings)
    {
        var longest = 0.0;

        foreach (var r in readings)
        {
            longest = Math.Max(longest, Measure(r.Name, CaptionSize, bold: false).Width);
            longest = Math.Max(longest, Measure($"{r.Value:0}%", ReadingSize, bold: true).Width);
            longest = Math.Max(longest, Measure(r.Note, CaptionSize, bold: false).Width);
        }

        return longest;
    }

    private static FormattedText Measure(string text, double size, bool bold) => new(
        text, CultureInfo.CurrentCulture, FlowDirection.LeftToRight,
        new Typeface(FontFamily.Default, FontStyle.Normal,
                     bold ? FontWeight.Bold : FontWeight.Normal),
        size, Brushes.White);

    /// <summary>Сама фигура: приглушённая заливка и светящийся контур.</summary>
    private void DrawFigure(DrawingContext context, double originX, double originY, double scale)
    {
        var move = Matrix.CreateScale(scale, scale) * Matrix.CreateTranslation(originX, originY);

        // Двигаем не каждую фигуру по отдельности, а систему координат: пути
        // описаны в собственной сетке фигуры и не должны знать ни про размер
        // окна, ни про место на нём.
        using var _ = context.PushTransform(move);

        // Толщина пера задаётся в единицах фигуры — вместе с координатами её
        // растянет то же преобразование. Полединицы при обычном масштабе дают
        // примерно пиксель.
        var thickness = 0.5;

        foreach (var (part, shape) in Silhouette.Parts())
        {
            var load = LoadFor(part);

            var body = Palette.PlateFor(Substance.Body, load);
            var edge = Palette.EdgeFor(Substance.Body, load);

            // Заливка приглушена, контур яркий. Это и делает картинку
            // голограммой, а не плоской аппликацией: светится край, а не пятно.
            context.DrawGeometry(
                new SolidColorBrush(body, 0.3),
                new Pen(new SolidColorBrush(edge, 0.95), thickness),
                shape);
        }
    }

    /// <summary>Свечение в груди — общая загрузка процессора.</summary>
    private void DrawCore(DrawingContext context, double originX, double originY, double scale)
    {
        var center = Place(originX, originY, scale, Silhouette.Core);
        var color = Palette.PlateFor(Substance.Glow, Cpu);
        var radius = Math.Max(2.5, 3.4 * scale);

        // Три круга друг в друге вместо одного: у настоящего свечения нет
        // резкого края, и такой градиент дешевле и надёжнее размытия.
        context.DrawEllipse(new SolidColorBrush(color, 0.16), null, center, radius * 2.6, radius * 2.6);
        context.DrawEllipse(new SolidColorBrush(color, 0.32), null, center, radius * 1.6, radius * 1.6);
        context.DrawEllipse(new SolidColorBrush(color, 0.95), null, center, radius, radius);
    }

    /// <summary>
    /// Выноски: линия от части фигуры к числу сбоку.
    ///
    /// Цвет показывает состояние, но не называет величину. Пока подписи стояли
    /// отдельным столбцом, приходилось догадываться, какая из них к какой части
    /// относится; линия снимает вопрос.
    /// </summary>
    private void DrawPointers(DrawingContext context, double originX, double originY,
                              double scale, double width, double sideRoom, Reading[] readings)
    {
        foreach (var r in readings)
        {
            var anchor = Silhouette.Anchor(r.Part);
            var from = Place(originX, originY, scale, new Point(anchor.X * r.Side, anchor.Y));

            var endX = r.Side < 0 ? sideRoom - 12 : width - sideRoom + 12;

            // Небольшой излом вместо прямой: так виднее, куда ведёт линия,
            // когда выносок несколько и они идут рядом.
            var elbow = new Point(from.X + (endX - from.X) * 0.5, from.Y);
            var end = new Point(endX, from.Y);

            var color = LoadToBrushConverter.ColorFor(r.Value);
            var pen = new Pen(new SolidColorBrush(color, 0.45), 1);

            context.DrawLine(pen, from, elbow);
            context.DrawLine(pen, elbow, end);
            context.DrawEllipse(new SolidColorBrush(color, 0.9), null, from, 2.5, 2.5);

            DrawReading(context, r, end, color);
        }
    }

    /// <summary>Название подсистемы, её число и пояснение у конца выноски.</summary>
    private void DrawReading(DrawingContext context, Reading r, Point end, Color color)
    {
        var caption = Measure(r.Name, CaptionSize, bold: false);
        caption.SetForegroundBrush(new SolidColorBrush(Color.FromRgb(0x8A, 0x97, 0xA8)));

        var reading = Measure($"{r.Value:0}%", ReadingSize, bold: true);
        reading.SetForegroundBrush(new SolidColorBrush(color));

        var hint = Measure(r.Note, CaptionSize, bold: false);
        hint.SetForegroundBrush(new SolidColorBrush(Color.FromRgb(0x64, 0x70, 0x80)));

        // Подпись уходит в поле, а не наезжает на фигуру: слева выравниваем по
        // правому краю, справа по левому.
        double X(double textWidth) => r.Side < 0 ? end.X - textWidth - 6 : end.X + 6;

        context.DrawText(caption, new Point(X(caption.Width), end.Y - 24));
        context.DrawText(reading, new Point(X(reading.Width), end.Y - 13));
        context.DrawText(hint, new Point(X(hint.Width), end.Y + 6));
    }

    /// <summary>
    /// Показание подсистемы, которой принадлежит часть.
    ///
    /// Руки и свечение в груди показывают процессор: руки — то, чем работают,
    /// и загруженный процессор виден по ним первым.
    /// </summary>
    private double LoadFor(BodyPart part) => part switch
    {
        BodyPart.Head => Gpu,
        BodyPart.Torso => Ram,
        BodyPart.Arms => Cpu,
        BodyPart.Core => Cpu,
        BodyPart.Legs => Disk,
        _ => 0,
    };
}
