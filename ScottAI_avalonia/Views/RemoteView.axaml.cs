using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace ScottAI.Avalonia.Views;

/// <summary>
/// Раздел «Удалённо». Своей логики не имеет — всё приходит из RemoteViewModel.
/// </summary>
public partial class RemoteView : UserControl
{
    public RemoteView()
    {
        InitializeComponent();
    }

    private void InitializeComponent() => AvaloniaXamlLoader.Load(this);
}
