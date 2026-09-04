using Avalonia.Controls;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.Views;

public partial class MacrosView : UserControl
{
    public MacrosView()
    {
        InitializeComponent();
        ItemsStagger.Attach(MacrosList);
    }
}
