using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace ScottAI.Avalonia.Views;

/// <summary>
/// Раздел «Внешний вид». Своей логики не имеет: всё приходит из
/// AppearanceViewModel, а само оформление живёт в ThemeService.
/// </summary>
public partial class AppearanceView : UserControl
{
    public AppearanceView()
    {
        InitializeComponent();
    }

    private void InitializeComponent() => AvaloniaXamlLoader.Load(this);
}
