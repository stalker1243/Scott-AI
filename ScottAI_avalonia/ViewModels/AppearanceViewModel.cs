using System.Collections.ObjectModel;
using System.Linq;
using Avalonia.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>
/// Внешний вид: стиль, тема, цвет и значок.
///
/// Раньше это была третья вкладка внутри Настроек. Настройки же — место, куда
/// заходят с вопросом («где включить тихий режим?»), а оформление перебирают,
/// глядя на программу: включил светлую тему, посмотрел, вернул тёмную. Прятать
/// такое за вкладкой внутри раздела незачем.
///
/// Состояние здесь — не источник правды, а отражение: само оформление живёт в
/// ThemeService и применяется ещё до создания окна, при запуске. Страница лишь
/// приводит в соответствие положение переключателей.
/// </summary>
public partial class AppearanceViewModel : ViewModelBase
{
    /// <summary>Тёмная или светлая — только для стиля Classic.</summary>
    [ObservableProperty]
    private bool _isDark = SettingsStore.Current.IsDark;

    /// <summary>"classic" | "glass" | "terminal" | "dashboard".</summary>
    [ObservableProperty]
    private string _currentStyle = SettingsStore.Current.Style;

    public ObservableCollection<AccentSwatch> AccentSwatches { get; } = new(
        ThemeService.AccentPalette.Select(h => new AccentSwatch(h)));

    [ObservableProperty]
    private string _currentAccentHex = "#3B82F6";

    [ObservableProperty]
    private double _glassOpacity = ThemeService.GlassOpacityPercent;

    /// <summary>
    /// Значок программы: тёмный или светлый.
    ///
    /// Привязывать его к теме лаунчера нельзя: тема окна и тема панели задач у
    /// человека независимы, и тёмный значок на тёмной панели пропадает.
    /// </summary>
    [ObservableProperty]
    private string _iconVariant = SettingsStore.Current.IconVariant;

    public AppearanceViewModel()
    {
        SyncAccentSelection();
    }

    partial void OnGlassOpacityChanged(double value)
    {
        ThemeService.SetGlassOpacity(value);
        PersistTheme();
    }

    /// <summary>
    /// Отметить цвет, который сейчас в деле.
    ///
    /// Зовётся и при заходе на страницу: цвет мог смениться из панели в углу
    /// окна, и страница, показывающая прежнюю отметку, врала бы.
    /// </summary>
    public void SyncAccentSelection()
    {
        CurrentAccentHex = ThemeService.CurrentAccentHex;

        foreach (var swatch in AccentSwatches)
        {
            swatch.IsSelected = string.Equals(swatch.Hex, CurrentAccentHex,
                System.StringComparison.OrdinalIgnoreCase);
        }
    }

    /// <summary>
    /// Запомнить оформление на следующий запуск.
    ///
    /// Снимок берётся с ThemeService, а не с полей страницы: акцент он
    /// сбрасывает сам при смене стиля, и только он знает, какой цвет в итоге
    /// применён.
    /// </summary>
    private void PersistTheme()
    {
        var settings = SettingsStore.Current;
        settings.Style = CurrentStyle;
        settings.IsDark = ThemeService.IsDark;
        settings.AccentHex = ThemeService.CurrentAccentHex;
        settings.GlassOpacity = ThemeService.GlassOpacityPercent;
        SettingsStore.SaveCurrent();
    }

    /// <summary>
    /// Перечитать оформление из настроек.
    ///
    /// Нужно после сброса, который делается в другом разделе: без этого
    /// переключатели показывали бы прежнее до перезапуска лаунчера, хотя окно
    /// уже выглядит по-новому.
    /// </summary>
    public void ReloadFromSettings()
    {
        var settings = SettingsStore.Current;

        IsDark = settings.IsDark;
        CurrentStyle = settings.Style;
        GlassOpacity = settings.GlassOpacity;
        IconVariant = settings.IconVariant;

        SyncAccentSelection();
    }

    [RelayCommand]
    private void SetStyleClassic()
    {
        CurrentStyle = "classic";
        ThemeService.ApplyStyle(AppStyle.Classic, IsDark);
        SyncAccentSelection();
        PersistTheme();
    }

    [RelayCommand]
    private void SetStyleGlass()
    {
        CurrentStyle = "glass";
        ThemeService.ApplyStyle(AppStyle.Glass);
        SyncAccentSelection();
        PersistTheme();
    }

    [RelayCommand]
    private void SetStyleTerminal()
    {
        CurrentStyle = "terminal";
        ThemeService.ApplyStyle(AppStyle.Terminal);
        SyncAccentSelection();
        PersistTheme();
    }

    [RelayCommand]
    private void SetStyleDashboard()
    {
        CurrentStyle = "dashboard";
        ThemeService.ApplyStyle(AppStyle.Dashboard);
        SyncAccentSelection();
        PersistTheme();
    }

    [RelayCommand]
    private void SetDark()
    {
        IsDark = true;
        if (CurrentStyle == "classic")
        {
            ThemeService.ApplyStyle(AppStyle.Classic, true);
            SyncAccentSelection();
        }
        PersistTheme();
    }

    [RelayCommand]
    private void SetLight()
    {
        IsDark = false;
        if (CurrentStyle == "classic")
        {
            ThemeService.ApplyStyle(AppStyle.Classic, false);
            SyncAccentSelection();
        }
        PersistTheme();
    }

    [RelayCommand]
    private void SetAccent(AccentSwatch swatch)
    {
        ThemeService.SetAccent(Color.Parse(swatch.Hex));
        SyncAccentSelection();
        PersistTheme();
    }

    [RelayCommand]
    private void SetIcon(string variant)
    {
        if (variant != AppIconService.Dark && variant != AppIconService.Light)
        {
            return;
        }

        IconVariant = variant;
        AppIconService.Apply(variant);
        SettingsStore.Current.IconVariant = variant;
        SettingsStore.SaveCurrent();
    }
}
