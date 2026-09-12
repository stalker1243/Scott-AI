using Avalonia.Controls;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.Views;

public partial class HomeView : UserControl
{
    public HomeView()
    {
        InitializeComponent();

        // Блоки въезжают по очереди, а голограмма появляется последней: она
        // самая заметная, и пусть взгляд дойдёт до неё, прочитав приветствие.
        Loaded += (_, _) => _ = UiAnimations.StaggerIn(
            new Control[] { Greeting, ExamplesBlock, Actions, Hologram },
            delayMs: 90);
    }
}
