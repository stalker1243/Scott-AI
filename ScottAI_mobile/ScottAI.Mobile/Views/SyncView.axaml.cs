using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace ScottAI.Mobile.Views;

public partial class SyncView : UserControl
{
    public SyncView()
    {
        InitializeComponent();
    }

    private void InitializeComponent() => AvaloniaXamlLoader.Load(this);
}
