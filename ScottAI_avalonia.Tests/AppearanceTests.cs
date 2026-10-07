using System;
using Avalonia.Media;
using ScottAI.Avalonia.Services;
using ScottAI.Avalonia.ViewModels;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Раздел «Внешний вид».
///
/// Оформление переехало сюда из третьей вкладки Настроек. Переезд опасен тем,
/// что состояние страницы и настоящее оформление могут разойтись: само оно
/// живёт в ThemeService и применяется ещё до создания окна, а страница только
/// отражает его. Разойдясь, они показывают человеку одно, а делают другое.
///
/// Поэтому проверяется не «нажалась ли кнопка», а то, что выбранное дошло до
/// ThemeService и запомнилось на следующий запуск.
/// </summary>
[Collection("avalonia")]
public class AppearanceTests : IDisposable
{
    private readonly string _стиль = SettingsStore.Current.Style;
    private readonly bool _тёмная = SettingsStore.Current.IsDark;
    private readonly string _цвет = ThemeService.CurrentAccentHex;

    /// <summary>Вернуть оформление машины в прежний вид: оно настоящее, не тестовое.</summary>
    public void Dispose()
    {
        SettingsStore.Current.Style = _стиль;
        SettingsStore.Current.IsDark = _тёмная;
        SettingsStore.Current.AccentHex = _цвет;
        SettingsStore.SaveCurrent();

        ThemeService.ApplySaved(SettingsStore.Current);
    }

    [Fact]
    public void Смена_стиля_доходит_до_оформления()
    {
        var раздел = new AppearanceViewModel();

        раздел.SetStyleTerminalCommand.Execute(null);

        Assert.Equal("terminal", раздел.CurrentStyle);
        Assert.Equal(AppStyle.Terminal, ThemeService.CurrentStyle);
    }

    [Fact]
    public void Выбранный_стиль_переживает_перезапуск()
    {
        // Настройки читаются при следующем запуске — если выбор туда не попал,
        // окно откроется в прежнем виде, и человек решит, что кнопка не
        // работает.
        var раздел = new AppearanceViewModel();

        раздел.SetStyleGlassCommand.Execute(null);

        Assert.Equal("glass", SettingsStore.Current.Style);
    }

    [Fact]
    public void Светлая_тема_включается_только_для_classic()
    {
        // У Glass тему задаёт рабочий стол под окном, Terminal Pro тёмный по
        // замыслу. Переключатель для них и не показывается, но проверка нужна:
        // команду можно позвать и не из интерфейса.
        var раздел = new AppearanceViewModel();
        раздел.SetStyleTerminalCommand.Execute(null);

        раздел.SetLightCommand.Execute(null);

        Assert.False(раздел.IsDark, "положение переключателя должно запомниться");
        Assert.Equal(AppStyle.Terminal, ThemeService.CurrentStyle);
    }

    [Fact]
    public void Приборная_панель_включается_и_переживает_перезапуск()
    {
        var раздел = new AppearanceViewModel();

        раздел.SetStyleDashboardCommand.Execute(null);

        Assert.Equal(AppStyle.Dashboard, ThemeService.CurrentStyle);
        Assert.Equal("dashboard", SettingsStore.Current.Style);

        // Восстановление из файла — отдельный путь, и стиль, забытый в нём,
        // молча откатывался бы к Classic при каждом запуске.
        ThemeService.ApplyStyle(AppStyle.Classic);
        ThemeService.ApplySaved(SettingsStore.Current);

        Assert.Equal(AppStyle.Dashboard, ThemeService.CurrentStyle);
    }

    [Fact]
    public void У_приборной_панели_свой_янтарный_акцент()
    {
        // Синий акцент Classic на графите с тёплым текстом выглядит чужим:
        // стиль держится именно на температуре цвета.
        var раздел = new AppearanceViewModel();

        раздел.SetStyleDashboardCommand.Execute(null);

        Assert.Equal("#FFB020", ThemeService.CurrentAccentHex);
    }

    [Theory]
    [InlineData(AppStyle.Classic)]
    [InlineData(AppStyle.Terminal)]
    [InlineData(AppStyle.Dashboard)]
    public void Непрозрачный_фон_совпадает_с_фоном_окна(AppStyle стиль)
    {
        // BgOpaque — фон мастера первого запуска, который обязан закрывать
        // окно целиком. Раньше он выбирался своей цепочкой условий, и стиль,
        // в неё не попавший, получал чужой цвет: графитовое окно с синим
        // мастером поверх.
        ThemeService.ApplyStyle(стиль);

        var окно = (SolidColorBrush)global::Avalonia.Application.Current!.Resources["BgWindow"]!;
        var мастер = (SolidColorBrush)global::Avalonia.Application.Current!.Resources["BgOpaque"]!;

        Assert.Equal(окно.Color, мастер.Color);
    }

    [Fact]
    public void Смена_цвета_доходит_до_оформления_и_запоминается()
    {
        var раздел = new AppearanceViewModel();
        var фиолетовый = new AccentSwatch("#A855F7");

        раздел.SetAccentCommand.Execute(фиолетовый);

        Assert.Equal("#A855F7", ThemeService.CurrentAccentHex);
        Assert.Equal("#A855F7", SettingsStore.Current.AccentHex);
    }

    [Fact]
    public void Страница_догоняет_цвет_выбранный_в_панели_угла()
    {
        // Тот же цвет можно сменить кнопкой в углу окна, не заходя сюда.
        // Страница, показывающая прежнюю отметку, врала бы о том, какой цвет
        // сейчас в деле.
        var раздел = new AppearanceViewModel();

        ThemeService.SetAccent(Color.Parse("#F59E0B"));
        раздел.SyncAccentSelection();

        var отмеченный = System.Linq.Enumerable.Single(раздел.AccentSwatches, с => с.IsSelected);
        Assert.Equal("#F59E0B", отмеченный.Hex);
    }

    [Fact]
    public void После_сброса_переключатели_показывают_новое()
    {
        // Сброс делается в Настройках — в другом разделе. Без связи между ними
        // окно уже выглядело бы по-новому, а переключатели здесь показывали бы
        // прежнее до перезапуска лаунчера.
        var раздел = new AppearanceViewModel();
        раздел.SetStyleTerminalCommand.Execute(null);

        SettingsStore.Current.Style = "classic";
        SettingsStore.Current.IsDark = true;
        раздел.ReloadFromSettings();

        Assert.Equal("classic", раздел.CurrentStyle);
        Assert.True(раздел.IsDark);
    }

    [Fact]
    public void Значок_программы_переключается_и_запоминается()
    {
        var раздел = new AppearanceViewModel();
        var прежний = SettingsStore.Current.IconVariant;

        try
        {
            раздел.SetIconCommand.Execute(AppIconService.Light);

            Assert.Equal(AppIconService.Light, раздел.IconVariant);
            Assert.Equal(AppIconService.Light, SettingsStore.Current.IconVariant);
        }
        finally
        {
            раздел.SetIconCommand.Execute(прежний);
        }
    }

    [Fact]
    public void Незнакомый_значок_не_принимается()
    {
        // Значений всего два, и подставить третье — значит остаться вовсе без
        // значка: файла с таким именем в ресурсах нет.
        var раздел = new AppearanceViewModel();
        var прежний = раздел.IconVariant;

        раздел.SetIconCommand.Execute("неоновый");

        Assert.Equal(прежний, раздел.IconVariant);
    }
}
