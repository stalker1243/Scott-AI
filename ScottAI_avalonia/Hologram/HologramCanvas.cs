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

    public static readonly StyledProperty<SuitKind> SuitProperty =
        AvaloniaProperty.Register<HologramCanvas, SuitKind>(nameof(Suit));

    public double Gpu { get => GetValue(GpuProperty); set => SetValue(GpuProperty, value); }
    public double Cpu { get => GetValue(CpuProperty); set => SetValue(CpuProperty, value); }
    public double Ram { get => GetValue(RamProperty); set => SetValue(RamProperty, value); }
    public double Disk { get => GetValue(DiskProperty); set => SetValue(DiskProperty, value); }
    public SuitKind Suit { get => GetValue(SuitProperty); set => SetValue(SuitProperty, value); }

    static HologramCanvas()
    {
        // Перерисовываем на любое изменение: показания меняются раз в три
        // секунды, а смена костюма — вообще по нажатию.
        AffectsRender<HologramCanvas>(GpuProperty, CpuProperty, RamProperty, DiskProperty, SuitProperty);
        SuitProperty.Changed.AddClassHandler<HologramCanvas>((c, _) => c._mesh = null);
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

        _mesh ??= Suits.Build(Suit);

        // Снизу оставлено место под кольца проекции: фигура должна стоять над
        // ними, а не пересекаться с ними ногами.
        const double pedestal = 46;

        var scale = Projector.FitScale(_mesh, width, height - pedestal);
        var faces = Projector.Project(
            _mesh, _yaw, _pitch, scale, width / 2, (height - pedestal) / 2);

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

            var color = ColorFor(face.Part);

            // Заливка почти непрозрачная. Полупрозрачность в полсилы оказалась
            // худшим из вариантов: сквозь ближние коробки всё равно видно
            // дальние, и вместо брони получается стопка стеклянных ящиков.
            // Небольшой просвет остаётся — ровно настолько, чтобы фигура
            // читалась как проекция, а не как вырезанная из картона.
            var fill = new SolidColorBrush(color, 0.88 * face.Light);
            var edge = new SolidColorBrush(color, Math.Min(1.0, 1.15 * face.Light));

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

            context.DrawGeometry(fill, new Pen(edge, 1.1), geometry);
        }
    }

    /// <summary>
    /// Цвет части — по показанию её подсистемы.
    ///
    /// Плащ и отделка ничего не показывают и красятся нейтрально: иначе каждая
    /// складка спорила бы с показаниями за внимание, и смысл цвета пропал бы.
    /// </summary>
    private Color ColorFor(BodyPart part) => part switch
    {
        BodyPart.Head => LoadToBrushConverter.ColorFor(Gpu),
        BodyPart.Core => LoadToBrushConverter.ColorFor(Cpu),
        BodyPart.Torso => LoadToBrushConverter.ColorFor(Ram),
        BodyPart.Legs => LoadToBrushConverter.ColorFor(Disk),
        BodyPart.Arms => Neutral,
        BodyPart.Cape => Cloth,
        _ => Neutral,
    };

    private static readonly Color Neutral = Color.FromRgb(0x7D, 0xD3, 0xFC);
    private static readonly Color Cloth = Color.FromRgb(0x93, 0xC5, 0xFD);
}
