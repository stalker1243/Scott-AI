using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace ScottAI.Avalonia.Views;

/// <summary>
/// Раздел «Модель». Своей логики не имеет: всё приходит из AiModelViewModel.
/// </summary>
public partial class AiModelView : UserControl
{
    public AiModelView()
    {
        InitializeComponent();
    }

    private void InitializeComponent() => AvaloniaXamlLoader.Load(this);
}
