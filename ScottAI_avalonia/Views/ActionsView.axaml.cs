using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace ScottAI.Avalonia.Views;

/// <summary>
/// Раздел «Действия». Своей логики не имеет — всё приходит из ActionsViewModel.
/// </summary>
public partial class ActionsView : UserControl
{
    public ActionsView()
    {
        InitializeComponent();
    }

    private void InitializeComponent() => AvaloniaXamlLoader.Load(this);
}
