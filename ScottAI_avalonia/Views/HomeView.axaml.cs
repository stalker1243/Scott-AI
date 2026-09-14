using Avalonia.Controls;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.Views;

public partial class HomeView : UserControl
{
    public HomeView()
    {
        InitializeComponent();

        // Блоки въезжают по очереди, сверху вниз — в том порядке, в каком их
        // читают: имя, поле ввода, примеры, состояние микрофона.
        Loaded += (_, _) => _ = UiAnimations.StaggerIn(
            new Control[] { Logo, Title, AskBlock, ExamplesBlock, ListenBlock },
            delayMs: 70);
    }
}
