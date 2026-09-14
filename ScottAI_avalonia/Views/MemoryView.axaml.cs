using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace ScottAI.Avalonia.Views;

/// <summary>
/// Раздел «Память». Своей логики не имеет — всё приходит из MemoryViewModel.
/// </summary>
public partial class MemoryView : UserControl
{
    public MemoryView()
    {
        InitializeComponent();
    }

    private void InitializeComponent() => AvaloniaXamlLoader.Load(this);
}
