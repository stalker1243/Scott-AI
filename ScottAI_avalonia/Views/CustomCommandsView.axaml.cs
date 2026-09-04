using Avalonia.Controls;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.Views;

public partial class CustomCommandsView : UserControl
{
    public CustomCommandsView()
    {
        InitializeComponent();
        ItemsStagger.Attach(CommandsList);
    }
}
