using System.Collections.Generic;
using Avalonia;
using Avalonia.Media;
using Avalonia.Styling;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Mobile.Services;

namespace ScottAI.Mobile.ViewModels;

/// <summary>Один цвет в палитре — с именем, потому что выбирают глазами, а не кодом.</summary>
public partial class AccentChoice : ObservableObject
{
    public string Name { get; init; } = "";
    public string Hex { get; init; } = "";
    public IBrush Brush => new SolidColorBrush(Color.Parse(Hex));

    /// <summary>
    /// Выбран ли сейчас.
    ///
    /// Без отметки палитра отвечает на вопрос «какие цвета бывают», но не на
    /// «какой у меня стоит». Второй вопрос человек задаёт чаще.
    /// </summary>
    [ObservableProperty] private bool _selected;
}

/// <summary>
/// Внешний вид.
///
/// Тот же набор цветов, что в лаунчере на компьютере: это одна вещь на двух
/// экранах, и разные палитры создавали бы ощущение двух разных программ.
///
/// Всё применяется сразу, без кнопки «применить»: выбор цвета проверяют
/// глазами, а не памятью.
/// </summary>
public partial class AppearanceViewModel : ViewModelBase
{
    public List<AccentChoice> Accents { get; } = new()
    {
        new AccentChoice { Name = "Синий",      Hex = "#3B82F6" },
        new AccentChoice { Name = "Бирюзовый",  Hex = "#06B6D4" },
        new AccentChoice { Name = "Зелёный",    Hex = "#22C55E" },
        new AccentChoice { Name = "Фиолетовый", Hex = "#8B5CF6" },
        new AccentChoice { Name = "Розовый",    Hex = "#EC4899" },
        new AccentChoice { Name = "Янтарный",   Hex = "#F59E0B" },
        new AccentChoice { Name = "Красный",    Hex = "#EF4444" },
    };

    [ObservableProperty] private string _accent = SettingsStore.Current.Accent;
    [ObservableProperty] private bool _dark = SettingsStore.Current.Theme != "light";
    [ObservableProperty] private double _fontScale = SettingsStore.Current.FontScale;

    public AppearanceViewModel()
    {
        Отметить();
        Apply();
    }

    partial void OnAccentChanged(string value)
    {
        SettingsStore.Current.Accent = value;
        SettingsStore.Save();
        Отметить();
        Apply();
    }

    /// <summary>Название выбранного цвета — кружок сам по себе безымянный.</summary>
    public string AccentName
    {
        get
        {
            foreach (var цвет in Accents)
            {
                if (цвет.Hex == Accent)
                {
                    return цвет.Name;
                }
            }

            return "Свой";
        }
    }

    private void Отметить()
    {
        foreach (var цвет in Accents)
        {
            цвет.Selected = цвет.Hex == Accent;
        }

        OnPropertyChanged(nameof(AccentName));
    }

    partial void OnDarkChanged(bool value)
    {
        SettingsStore.Current.Theme = value ? "dark" : "light";
        SettingsStore.Save();
        Apply();
    }

    partial void OnFontScaleChanged(double value)
    {
        SettingsStore.Current.FontScale = value;
        SettingsStore.Save();
        Apply();
    }

    [RelayCommand]
    private void Choose(string? hex)
    {
        if (hex is not null)
        {
            Accent = hex;
        }
    }

    /// <summary>
    /// Применить к самому приложению.
    ///
    /// Цвет кладётся в ресурсы, а не в стили: так его подхватывают все экраны
    /// сразу, включая уже открытый, — иначе цвет менялся бы только там, куда
    /// человек ещё не заходил.
    /// </summary>
    public void Apply()
    {
        var приложение = Application.Current;
        if (приложение is null)
        {
            return;
        }

        приложение.RequestedThemeVariant = Dark ? ThemeVariant.Dark : ThemeVariant.Light;

        var цвет = Color.Parse(Accent);
        приложение.Resources["Accent"] = new SolidColorBrush(цвет);
        приложение.Resources["AccentColor"] = цвет;

        // Мягкая подложка того же цвета: ею залиты собственные реплики в чате.
        приложение.Resources["AccentSoft"] = new SolidColorBrush(цвет, 0.18);

        приложение.Resources["ChatFontSize"] = 15.0 * FontScale;
    }
}
