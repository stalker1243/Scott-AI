using System;
using System.Collections.Generic;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Media;
using Avalonia.Threading;
using ScottAI.Avalonia.Converters;

namespace ScottAI.Avalonia.Hologram;

/// <summary>
/// Объёмная фигура, показывающая состояние машины. Её можно крутить мышью.
///
/// Каждая часть отвечает за свою подсистему: голова — видеокарта, ядро в
/// груди — процессор, корпус — оперативная память, ноги — диск. Цвет меняется
/// от бирюзового через янтарный к красному, так что состояние читается одним
/// взглядом, без чтения цифр.
///
/// Рисуется своим отрисовщиком, а не готовым движком. Своего трёхмерного у
/// Avalonia нет, а тащить ради одной фигуры OpenGL — значит получить вторую
/// цепочку сборки и новый класс поломок на чужих машинах, где и без того
/// хватало «не запускается». Сотня строк математики делает ровно то, что нужно,
/// и проверяется обычными тестами.
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

    public double Gpu { get => GetValue(GpuProperty); set => SetValue(GpuProperty, value); }
    public double Cpu { get => GetValue(CpuProperty); set => SetValue(CpuProperty, value); }
    public double Ram { get => GetValue(RamProperty); set => SetValue(RamProperty, value); }
    public double Disk { get => GetValue(DiskProperty); set => SetValue(DiskProperty, value); }

    static HologramCanvas()
    {
        // Перерисовываем на любое изменение: показания меняются раз в три
        // секунды, а смена костюма — вообще по нажатию.
        AffectsRender<HologramCanvas>(GpuProperty, CpuProperty, RamProperty, DiskProperty);
    }

    // ==================== Поворот ====================

    /// <summary>Скорость самостоятельного вращения, оборотов в минуту.</summary>
    private const double IdleTurnsPerMinute = 1.6;

    /// <summary>Во сколько раз движение мыши переводится в поворот.</summary>
    private const double DragSensitivity = 0.011;

    /// <summary>
    /// Пределы наклона.
    ///
    /// Через полюс фигура переворачивается вверх ногами, и вернуть её оттуда
    /// мышью неочевидно. Ограничение мягче, чем кажется: смотреть на голограмму
    /// снизу всё равно незачем.
    /// </summary>
    private const double MaxPitch = 0.55;

    private double _yaw = 0.45;
    private double _pitch = 0.12;

    private bool _dragging;
    private Point _lastPointer;
    private DispatcherTimer? _spin;
    private Mesh? _mesh;

    /// <summary>Сколько времени фигура стоит нетронутой.</summary>
    private int _idleTicks;

    /// <summary>
    /// Через сколько тиков возобновляется самостоятельное вращение.
    ///
    /// Сразу подхватывать нельзя: человек повернул фигуру, чтобы рассмотреть, и
    /// она тут же уехала бы из-под рук. Три секунды — достаточно, чтобы это
    /// ощущалось как «отпустил и забыл».
    /// </summary>
    private const int IdleTicksBeforeSpin = 60;

    public HologramCanvas()
    {
        ClipToBounds = true;
        Cursor = new Cursor(StandardCursorType.Hand);
    }

    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);

        _spin = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(50) };
        _spin.Tick += (_, _) => Spin();
        _spin.Start();
    }

    protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
    {
        // Таймер держит ссылку на элемент: не остановив его, страница осталась
        // бы перерисовываться в памяти после закрытия.
        _spin?.Stop();
        _spin = null;

        base.OnDetachedFromVisualTree(e);
    }

    private void Spin()
    {
        if (_dragging)
        {
            return;
        }

        if (_idleTicks < IdleTicksBeforeSpin)
        {
            _idleTicks++;
            return;
        }

        _yaw += Math.PI * 2 * IdleTurnsPerMinute / 60 * 0.05;
        InvalidateVisual();
    }

    // ==================== Мышь ====================

    protected override void OnPointerPressed(PointerPressedEventArgs e)
    {
        base.OnPointerPressed(e);

        _dragging = true;
        _idleTicks = 0;
        _lastPointer = e.GetPosition(this);
        e.Pointer.Capture(this);
    }

    protected override void OnPointerMoved(PointerEventArgs e)
    {
        base.OnPointerMoved(e);

        if (!_dragging) return;

        var position = e.GetPosition(this);
        var dx = position.X - _lastPointer.X;
        var dy = position.Y - _lastPointer.Y;
        _lastPointer = position;

        _yaw += dx * DragSensitivity;
        _pitch = Math.Clamp(_pitch + dy * DragSensitivity, -MaxPitch, MaxPitch);

        InvalidateVisual();
    }

    protected override void OnPointerReleased(PointerReleasedEventArgs e)
    {
        base.OnPointerReleased(e);

        _dragging = false;
        _idleTicks = 0;
        e.Pointer.Capture(null);
    }

    // ==================== Отрисовка ====================

    public override void Render(DrawingContext context)
    {
        base.Render(context);

        var width = Bounds.Width;
        var height = Bounds.Height;
        if (width < 20 || height < 20) return;

        _mesh ??= Suits.Build();

        // Снизу оставлено место под кольца проекции: фигура должна стоять над
        // ними, а не пересекаться с ними ногами.
        const double pedestal = 26;

        var scale = Projector.FitScale(_mesh, width, height - pedestal);

        // Фигура ставится ногами на кольца, а не вешается серединой в середину.
        // Второе казалось очевидным и выглядело плохо: между ступнями и
        // кольцами оставался просвет в палец, и фигура висела в воздухе вместо
        // того, чтобы стоять в проекции.
        var centerY = Projector.GroundedCenterY(_mesh, scale, height - pedestal);

        var faces = Projector.Project(_mesh, _yaw, _pitch, scale, width / 2, centerY);

        foreach (var face in faces)
        {
            // Отвёрнутые грани пропускаем совсем.
            //
            // Сначала они рисовались еле заметно — казалось, что просвечивающие
            // рёбра добавят голограмме воздуха. На живой проверке вышло
            // обратное: сквозь ближние коробки просвечивали все дальние, и
            // вместо брони получалась путаница линий, в которой не разобрать ни
            // фигуры, ни цвета. Голограмма должна просвечивать чуть-чуть, а не
            // насквозь.
            if (!face.Facing) continue;

            var load = LoadFor(face.Part);

            // Пластина красится цветом доспеха, подкрашенным нагрузкой, и
            // притеняется по свету. Кромка светится цветом нагрузки заметно
            // сильнее: именно по кромкам состояние и читается с одного
            // взгляда, а металл при этом остаётся металлом.
            var plate = Palette.Shade(Palette.PlateFor(face.Part, load), face.Light * face.Tint);
            var rim = Palette.EdgeFor(face.Part, load);

            var cloth = face.Part == BodyPart.Cape;

            var fill = new SolidColorBrush(plate, cloth ? 0.55 : 0.95);
            var edge = new SolidColorBrush(rim, cloth ? 0.45 : 0.75);

            var geometry = new StreamGeometry();
            using (var sink = geometry.Open())
            {
                sink.BeginFigure(new Point(face.Points[0].X, face.Points[0].Y), isFilled: true);
                for (var i = 1; i < face.Points.Length; i++)
                {
                    sink.LineTo(new Point(face.Points[i].X, face.Points[i].Y));
                }
                sink.EndFigure(isClosed: true);
            }

            context.DrawGeometry(fill, new Pen(edge, cloth ? 0.7 : 1.0), geometry);
        }
    }

    /// <summary>
    /// Показание подсистемы, которой принадлежит часть.
    ///
    /// Плащ и отделка ничего не показывают: у них своя задача, и спорить с
    /// показаниями приборов за внимание им незачем.
    /// </summary>
    private double LoadFor(BodyPart part) => part switch
    {
        BodyPart.Head => Gpu,
        BodyPart.Core => Cpu,
        BodyPart.Torso => Ram,
        BodyPart.Legs => Disk,

        // Наплечники и наручи держат сторону кирасы: они её продолжение, и
        // собственного показания у них нет.
        BodyPart.Arms => Ram,

        _ => 0,
    };
}
