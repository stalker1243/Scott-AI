using System;
using System.Linq;
using Avalonia.Media;
using ScottAI.Avalonia.Services;
using ScottAI.Avalonia.ViewModels;
using Xunit;

namespace ScottAI.Avalonia.Tests;

/// <summary>
/// Панель выбора цвета, доступная с любой страницы.
///
/// Цвет и раньше можно было сменить — в Настройках, во вкладке «Оформление».
/// Беда не в числе нажатий, а в том, что цвет выбирают ГЛЯДЯ на программу:
/// понравился ли он, видно по той странице, которая сейчас открыта, а не по
/// странице настроек.
///
/// Проверяется здесь логика, а не вид: попасть мышью в кружок тридцати точек
/// автоматика не берётся — на живом окне это выходило через раз, и дважды
/// «промах» выглядел как «цвет не меняется».
/// </summary>
[Collection("avalonia")]
public class AccentPickerTests
{
    [Fact]
    public void Панель_закрыта_по_умолчанию()
    {
        // Постоянный ряд кружков в углу — украшение, которое смотрит на
        // человека каждый день, а нужно раз в месяц.
        Assert.False(new AccentPickerViewModel().IsOpen);
    }

    [Fact]
    public void Кнопка_открывает_и_закрывает()
    {
        var панель = new AccentPickerViewModel();

        панель.ToggleCommand.Execute(null);
        Assert.True(панель.IsOpen);

        панель.ToggleCommand.Execute(null);
        Assert.False(панель.IsOpen);
    }

    [Fact]
    public void Нажатие_мимо_панели_её_закрывает()
    {
        // Иначе закрывать пришлось бы той же кнопкой, что открыла, — а рука к
        // этому моменту уже в другом месте экрана.
        var панель = new AccentPickerViewModel();
        панель.ToggleCommand.Execute(null);

        панель.CloseCommand.Execute(null);

        Assert.False(панель.IsOpen);
    }

    [Fact]
    public void Выбор_меняет_цвет_программы()
    {
        var панель = new AccentPickerViewModel();
        var прежний = ThemeService.CurrentAccentHex;

        try
        {
            var зелёный = панель.Swatches.First(с => с.Hex == "#22C55E");
            панель.PickCommand.Execute(зелёный);

            Assert.Equal("#22C55E", ThemeService.CurrentAccentHex);
        }
        finally
        {
            ThemeService.SetAccent(Color.Parse(прежний));
        }
    }

    [Fact]
    public void Выбранный_цвет_отмечен()
    {
        var панель = new AccentPickerViewModel();
        var прежний = ThemeService.CurrentAccentHex;

        try
        {
            var фиолетовый = панель.Swatches.First(с => с.Hex == "#A855F7");
            панель.PickCommand.Execute(фиолетовый);

            Assert.True(фиолетовый.IsSelected, "выбранный цвет не отмечен галочкой");
            Assert.All(панель.Swatches.Where(с => с != фиолетовый),
                с => Assert.False(с.IsSelected, "отмечено больше одного цвета"));
        }
        finally
        {
            ThemeService.SetAccent(Color.Parse(прежний));
        }
    }

    [Fact]
    public void Панель_не_закрывается_после_выбора()
    {
        // Цвета перебирают подряд, сравнивая. Панель, закрывающаяся после
        // каждого нажатия, мешала бы этому больше всего.
        var панель = new AccentPickerViewModel();
        var прежний = ThemeService.CurrentAccentHex;

        try
        {
            панель.ToggleCommand.Execute(null);
            панель.PickCommand.Execute(панель.Swatches.First());

            Assert.True(панель.IsOpen);
        }
        finally
        {
            ThemeService.SetAccent(Color.Parse(прежний));
        }
    }

    [Fact]
    public void Открытие_сверяет_отметку_с_текущим_цветом()
    {
        // Цвет могли сменить в Настройках, пока панель была закрыта. Открывшись
        // с прежней галочкой, она врала бы о том, какой цвет сейчас в деле.
        var панель = new AccentPickerViewModel();
        var прежний = ThemeService.CurrentAccentHex;

        try
        {
            ThemeService.SetAccent(Color.Parse("#EF4444"));

            панель.ToggleCommand.Execute(null);

            var отмеченный = панель.Swatches.Single(с => с.IsSelected);
            Assert.Equal("#EF4444", отмеченный.Hex);
        }
        finally
        {
            ThemeService.SetAccent(Color.Parse(прежний));
        }
    }

    [Fact]
    public void Набор_цветов_тот_же_что_и_в_настройках()
    {
        // Список хранится в службе темы — один на оба места, откуда цвет можно
        // сменить. Разойдись они, человек нашёл бы в одном месте цвет, которого
        // нет в другом, и не понял бы, какое из двух настоящее.
        var вПанели = new AccentPickerViewModel().Swatches.Select(с => с.Hex).ToArray();

        Assert.Equal(ThemeService.AccentPalette, вПанели);
        Assert.Equal(6, вПанели.Length);
    }
}
