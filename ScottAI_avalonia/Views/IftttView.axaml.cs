using Avalonia.Controls;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.Views;

public partial class IftttView : UserControl
{
    public IftttView()
    {
        InitializeComponent();
        ItemsStagger.Attach(RulesList);
    }
}
