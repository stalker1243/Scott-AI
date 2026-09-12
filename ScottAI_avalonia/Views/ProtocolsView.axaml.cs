using Avalonia.Controls;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.Views;

public partial class ProtocolsView : UserControl
{
    public ProtocolsView()
    {
        InitializeComponent();
        ItemsStagger.Attach(ProtocolsList);
    }
}
