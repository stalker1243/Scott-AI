using System;
using System.Collections.Generic;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Media.Imaging;
using Avalonia.Platform;

namespace ScottAI.Avalonia.Services;

/// <summary>
/// Выбор иконки приложения: тёмная или светлая.
///
/// Двух вариантов хватает потому, что различаются они фоном самой иконки:
/// тёмная со свечением хороша на тёмном интерфейсе и в тёмной панели задач,
/// светлая — на белом. Тема лаунчера и системная тема панели задач у человека
/// могут не совпадать, поэтому выбор оставлен ему, а не привязан к теме
/// автоматически.
///
/// Иконка .exe в этот выбор не входит: она вшивается в файл при сборке и
/// поменять её на лету нельзя.
/// </summary>
public static class AppIconService
{
    public const string Dark = "dark";
    public const string Light = "light";

    // Имя сборки берётся на месте, а не пишется строкой: программу однажды
    // переименовали (ScottAI.Avalonia → ScottAI), и зашитые адреса ресурсов
    // перестали существовать. Лаунчер после этого не запускался вовсе —
    // молча, потому что падал ещё до появления окна.
    private static readonly string Root =
        $"avares://{System.Reflection.Assembly.GetExecutingAssembly().GetName().Name}/Assets";

    private static readonly Dictionary<string, (string Icon, string Logo)> Variants = new()
    {
        [Dark] = ($"{Root}/scott.ico", $"{Root}/scott-logo.png"),
        [Light] = ($"{Root}/scott-light.ico", $"{Root}/scott-logo-light.png"),
    };

    public static string Current { get; private set; } = Dark;

    /// <summary>Сработает после смены — сайдбар слушает, чтобы перерисовать логотип.</summary>
    public static event Action<string>? IconChanged;

    public static bool IsKnown(string? variant) => variant is not null && Variants.ContainsKey(variant);

    /// <summary>Логотип для интерфейса. Загружается заново на каждый вызов: картинка
    /// маленькая, а держать её в поле — значит рисковать обращением к освобождённой.</summary>
    public static Bitmap? LoadLogo(string? variant = null)
    {
        var key = IsKnown(variant) ? variant! : Current;
        try
        {
            return new Bitmap(AssetLoader.Open(new Uri(Variants[key].Logo)));
        }
        catch (Exception e)
        {
            // Без логотипа программа некрасива, но работает. Раньше здесь
            // вылетало исключение прямо при создании главного окна, и человек
            // видел ровно ничего: ярлык нажат, окна нет.
            LauncherLog.WriteError($"не удалось загрузить логотип ({Variants[key].Logo})", e);
            return null;
        }
    }

    public static WindowIcon? LoadWindowIcon(string? variant = null)
    {
        var key = IsKnown(variant) ? variant! : Current;
        try
        {
            return new WindowIcon(AssetLoader.Open(new Uri(Variants[key].Icon)));
        }
        catch (Exception e)
        {
            LauncherLog.WriteError($"не удалось загрузить иконку ({Variants[key].Icon})", e);
            return null;
        }
    }

    /// <summary>
    /// Применить вариант к окну, трею и логотипу в сайдбаре.
    ///
    /// Ошибки здесь намеренно проглатываются: иконка — вещь приятная, но
    /// падать из-за неё лаунчер не должен, а трей на некоторых системах может
    /// быть недоступен вовсе.
    /// </summary>
    public static void Apply(string? variant)
    {
        Current = IsKnown(variant) ? variant! : Dark;

        try
        {
            var icon = LoadWindowIcon(Current);
            if (icon is null)
            {
                IconChanged?.Invoke(Current);
                return;
            }

            if (Application.Current?.ApplicationLifetime
                is global::Avalonia.Controls.ApplicationLifetimes.IClassicDesktopStyleApplicationLifetime desktop
                && desktop.MainWindow is not null)
            {
                desktop.MainWindow.Icon = icon;
            }

            if (Application.Current is not null)
            {
                foreach (var tray in TrayIcon.GetIcons(Application.Current) ?? new TrayIcons())
                {
                    tray.Icon = icon;
                }
            }
        }
        catch (Exception)
        {
            // Не нашлось ресурса или система не даёт трей — оставляем как есть.
        }

        IconChanged?.Invoke(Current);
    }
}
