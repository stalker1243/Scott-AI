using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace ScottAI.Avalonia.Views;

/// <summary>
/// Раздел «О программе». Своей логики не имеет — всё приходит из AboutViewModel.
/// </summary>
public partial class AboutView : UserControl
{
    public AboutView()
    {
        InitializeComponent();
    }

    private void InitializeComponent() => AvaloniaXamlLoader.Load(this);
}
