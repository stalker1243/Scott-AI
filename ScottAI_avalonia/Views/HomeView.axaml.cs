using Avalonia.Controls;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.Views;

public partial class HomeView : UserControl
{
    public HomeView()
    {
        InitializeComponent();
        Loaded += (_, _) => _ = UiAnimations.StaggerIn(new Control[] { CpuCard, RamCard, ProcessCard, LaunchButton });
    }
}
