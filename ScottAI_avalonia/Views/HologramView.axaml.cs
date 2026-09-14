using Avalonia.Controls;
using Avalonia.Markup.Xaml;

namespace ScottAI.Avalonia.Views;

/// <summary>
/// Голограмма состояния машины — в разделе «Система».
///
/// Стояла на главной странице, но отвечала там на вопрос, которого при запуске
/// помощника никто не задаёт. Рядом с карточками нагрузки и списком процессов
/// она на своём месте.
///
/// Своей логики не имеет: всё, что она показывает, приходит из SystemViewModel
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
