using System.Collections.ObjectModel;
using System.Linq;
using Avalonia.Media;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

/// <summary>
/// Выбор акцентного цвета, доступный с любой страницы.
///
/// Цвет и раньше можно было сменить — в Настройках, во вкладке «Оформление», в
/// третьем разделе сверху. Беда не в числе нажатий, а в том, что цвет
/// выбирают ГЛЯДЯ на программу: понравился ли он, видно по той странице,
/// которая сейчас открыта, а не по странице настроек. Отсюда его меняют, не
/// уходя со своего места, и сразу видят результат.
///
/// Панель прячется за кнопкой и по умолчанию закрыта: постоянный ряд кружков в
/// углу — это украшение, которое смотрит на человека каждый день, а нужно оно
/// раз в месяц.
/// </summary>
public partial class AccentPickerViewModel : ViewModelBase
{
    /// <summary>
    /// Те же цвета, что и в Настройках: список хранится в службе темы, один на
    /// оба места.
    /// </summary>
    public ObservableCollection<AccentSwatch> Swatches { get; } =
        new(ThemeService.AccentPalette.Select(hex => new AccentSwatch(hex)));

    /// <summary>Открыта ли панель. Закрыта по умолчанию.</summary>
    [ObservableProperty]
    private bool _isOpen;

    public AccentPickerViewModel()
    {
        Sync();
    }

    [RelayCommand]
    private void Toggle()
    {
        IsOpen = !IsOpen;

        // Отметку сверяем при каждом открытии: цвет могли сменить в Настройках,
        // и панель, открывшаяся с прежней галочкой, врала бы о текущем.
        if (IsOpen)
        {
            Sync();
        }
    }

    [RelayCommand]
    private void Close() => IsOpen = false;

    [RelayCommand]
    private void Pick(AccentSwatch swatch)
    {
        ThemeService.SetAccent(Color.Parse(swatch.Hex));
        Sync();

        // Сохраняем сразу: цвет выбирают один раз и ждут, что он останется. К
        // тому же панель не имеет кнопки «применить» — ей неоткуда взяться,
        // когда результат виден мгновенно.
        var settings = SettingsStore.Current;
        settings.AccentHex = ThemeService.CurrentAccentHex;
        SettingsStore.SaveCurrent();

        // Панель не закрываем: цвета перебирают подряд, сравнивая, и
        // закрывающаяся после каждого нажатия панель мешала бы этому больше
        // всего.
    }

    /// <summary>Отметить тот кружок, который сейчас в деле.</summary>
    public void Sync()
    {
        var текущий = ThemeService.CurrentAccentHex;
        foreach (var swatch in Swatches)
        {
            swatch.IsSelected = string.Equals(swatch.Hex, текущий,
                System.StringComparison.OrdinalIgnoreCase);
        }
    }
}
