using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace ScottAI.Mobile.Views;

public partial class AppearanceView : UserControl
{
    public AppearanceView()
    {
        InitializeComponent();
    }

    private void InitializeComponent() => AvaloniaXamlLoader.Load(this);
}
