using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace ScottAI.Avalonia.Views;

/// <summary>
/// Голограмма состояния машины на главной странице.
///
/// Своей логики не имеет: всё, что она показывает, приходит из HomeViewModel
/// через привязки, а движение задано стилями. Класс нужен только затем, чтобы
/// разметка загрузилась.
/// </summary>
public partial class HologramView : UserControl
{
    public HologramView()
    {
        InitializeComponent();
    }

    private void InitializeComponent() => AvaloniaXamlLoader.Load(this);
}
