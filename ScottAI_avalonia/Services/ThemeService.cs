using System;
using System.Collections.Generic;
using Avalonia;
using Avalonia.Media;

namespace ScottAI.Avalonia.Services;

public enum AppStyle
{
    Classic,
    Glass,
    Terminal,
}

/// <summary>
/// Переключение стиля (Classic/Glass/Terminal Pro — те же три, что и в Tauri-версии)
/// и акцентного цвета в рантайме. DynamicResource переоценивается автоматически,
/// когда ключ в Application.Current.Resources меняется — переписываем значения,
/// перестраивать дерево контролов не нужно.
///
/// "Glass" здесь — настоящая прозрачность окна через встроенную в Avalonia
/// поддержку TransparencyLevelHint (AcrylicBlur/Blur), а не только цветовая
/// имитация: сама Avalonia управляет окном (в отличие от прошлой попытки на
/// Rust/Slint через отдельный крейт window_vibrancy, где не было прямого
/// доступа к WinAPI-хендлу — NoWindowHandle/NotSupported), поэтому здесь это
/// работает надёжно. Уровень прозрачности фона регулируется GlassOpacityPercent.
/// MainWindow подписывается на StyleApplied и переключает TransparencyLevelHint.
/// </summary>
public static class ThemeService
{
    public static AppStyle CurrentStyle { get; private set; } = AppStyle.Classic;
    public static bool IsDark { get; private set; } = true;
    public static string CurrentAccentHex { get; private set; } = "#3B82F6";

    /// <summary>Непрозрачность фона в стиле Glass, 15-100%. Ниже 15 — контент нечитаем.</summary>
    public static double GlassOpacityPercent { get; private set; } = 55;

    /// <summary>Срабатывает после применения стиля — MainWindow слушает, чтобы включить/выключить OS-блюр и фоновые декорации.</summary>
    public static event Action<AppStyle>? StyleApplied;

    private static readonly Dictionary<string, Color> ClassicDark = new()
    {
        ["BgWindow"] = Color.Parse("#10161F"),
        ["BgSidebar"] = Color.Parse("#0D1420"),
        ["BgTopbar"] = Color.Parse("#131B28"),
        ["BgSurface"] = Color.Parse("#1A2332"),
        ["BgElevated"] = Color.Parse("#212C3D"),
        ["TextPrimary"] = Color.Parse("#F3F4F6"),
        ["TextSecondary"] = Color.Parse("#9CA3AF"),
        ["TextMuted"] = Color.Parse("#6B7280"),
        ["BorderColor"] = Color.Parse("#2A3547"),
    };

    private static readonly Dictionary<string, Color> ClassicLight = new()
    {
        ["BgWindow"] = Color.Parse("#F1F2F5"),
        ["BgSidebar"] = Color.Parse("#FFFFFF"),
        ["BgTopbar"] = Color.Parse("#FFFFFF"),
        ["BgSurface"] = Color.Parse("#FFFFFF"),
        ["BgElevated"] = Color.Parse("#F3F4F6"),
        ["TextPrimary"] = Color.Parse("#111827"),
        ["TextSecondary"] = Color.Parse("#6B7280"),
        ["TextMuted"] = Color.Parse("#9CA3AF"),
        ["BorderColor"] = Color.Parse("#E2E5EB"),
    };

    private static readonly Dictionary<string, Color> Glass = new()
    {
        ["BgWindow"] = Color.Parse("#0B1220"),
        ["BgSidebar"] = Color.Parse("#0A1020"),
        ["BgTopbar"] = Color.Parse("#0A1020"),
        ["BgSurface"] = Color.Parse("#141D30"),
        ["BgElevated"] = Color.Parse("#1D2A45"),
        ["TextPrimary"] = Color.Parse("#FFFFFF"),
        ["TextSecondary"] = Color.Parse("#CBD5E1"),
        ["TextMuted"] = Color.Parse("#94A3B8"),
        ["BorderColor"] = Color.FromArgb(60, 255, 255, 255),
    };

    private static readonly Dictionary<string, Color> Terminal = new()
    {
        ["BgWindow"] = Color.Parse("#05070A"),
        ["BgSidebar"] = Color.Parse("#090C11"),
        ["BgTopbar"] = Color.Parse("#090C11"),
        ["BgSurface"] = Color.Parse("#0D1117"),
        ["BgElevated"] = Color.Parse("#131A23"),
        ["TextPrimary"] = Color.Parse("#E6FAFF"),
        ["TextSecondary"] = Color.Parse("#7FE7FF"),
        ["TextMuted"] = Color.Parse("#4A6572"),
        ["BorderColor"] = Color.FromArgb(51, 0, 255, 242),
    };

    private static readonly Dictionary<AppStyle, string> DefaultAccents = new()
    {
        [AppStyle.Classic] = "#3B82F6",
        [AppStyle.Glass] = "#60A5FA",
        [AppStyle.Terminal] = "#00FFF2",
    };

    /// <summary>Переключить стиль. dark значим только для Classic (Glass/Terminal — всегда тёмные, как в Tauri-версии).</summary>
    public static void ApplyStyle(AppStyle style, bool dark = true)
    {
        CurrentStyle = style;
        IsDark = dark;

        var palette = style switch
        {
            AppStyle.Glass => Glass,
            AppStyle.Terminal => Terminal,
            _ => dark ? ClassicDark : ClassicLight,
        };

        var resources = Application.Current!.Resources;
        foreach (var (key, color) in palette)
        {
            resources[key] = new SolidColorBrush(color);
        }

        if (style == AppStyle.Glass)
        {
            ApplyGlassOpacity();
        }

        resources["AppFontFamily"] = style == AppStyle.Terminal
            ? new FontFamily("Consolas, Cascadia Code, Courier New, monospace")
            : new FontFamily("Segoe UI, sans-serif");

        SetAccent(Color.Parse(DefaultAccents[style]));
        StyleApplied?.Invoke(style);
    }

    /// <summary>
    /// Восстановить оформление, сохранённое с прошлого запуска.
    ///
    /// Порядок важен: ApplyStyle сбрасывает акцент на цвет по умолчанию для
    /// стиля, поэтому сохранённый акцент ставится после него, иначе он был бы
    /// затёрт. Прозрачность выставляется до стиля, чтобы Glass отрисовался
    /// сразу с нужной, а не мигнул чужой на старте.
    /// </summary>
    public static void ApplySaved(LauncherSettings settings)
    {
        GlassOpacityPercent = Math.Clamp(settings.GlassOpacity, 15, 100);

        var style = settings.Style switch
        {
            "glass" => AppStyle.Glass,
            "terminal" => AppStyle.Terminal,
            _ => AppStyle.Classic,
        };

        ApplyStyle(style, settings.IsDark);

        try
        {
            SetAccent(Color.Parse(settings.AccentHex));
        }
        catch (FormatException)
        {
            // В файле оказалась не пригодная к разбору строка — оставляем цвет
            // по умолчанию, который уже выставил ApplyStyle.
        }
    }

    /// <summary>Изменить непрозрачность фона в Glass-стиле "на лету". Ничего не делает вне Glass — значение просто запоминается на будущее.</summary>
    public static void SetGlassOpacity(double percent)
    {
        GlassOpacityPercent = Math.Clamp(percent, 15, 100);
        if (CurrentStyle == AppStyle.Glass)
        {
            ApplyGlassOpacity();
        }
    }

    /// <summary>Переписывает фоновые ключи Glass-палитры с учётом текущей непрозрачности — эти брэши уходят
    /// в реальное окно с TransparencyLevelHint=AcrylicBlur/Blur, поэтому там, где alpha меньше 255, сквозь
    /// приложение виден настоящий блюр рабочего стола, а не просто имитация цветом.</summary>
    private static void ApplyGlassOpacity()
    {
        var resources = Application.Current!.Resources;
        var windowAlpha = (byte)Math.Round(GlassOpacityPercent / 100.0 * 255);
        var surfaceAlpha = (byte)Math.Min(255, windowAlpha + 35);

        void SetBg(string key, byte alpha)
        {
            var c = Glass[key];
            resources[key] = new SolidColorBrush(Color.FromArgb(alpha, c.R, c.G, c.B));
        }

        SetBg("BgWindow", windowAlpha);
        SetBg("BgSidebar", windowAlpha);
        SetBg("BgTopbar", windowAlpha);
        SetBg("BgSurface", surfaceAlpha);
        SetBg("BgElevated", surfaceAlpha);
    }

    public static void SetAccent(Color color)
    {
        var resources = Application.Current!.Resources;
        resources["Accent"] = new SolidColorBrush(color);
        // Полупрозрачная версия акцента — для фоновых "заливок" активных элементов
        // (вкладки, пункты меню), чтобы смена цвета ощущалась не только в тонкой
        // рамке/иконке, а в заметной площади заливки.
        resources["AccentSoft"] = new SolidColorBrush(Color.FromArgb(54, color.R, color.G, color.B));
        resources["AccentSofter"] = new SolidColorBrush(Color.FromArgb(34, color.R, color.G, color.B));
        CurrentAccentHex = $"#{color.R:X2}{color.G:X2}{color.B:X2}";
    }
}
