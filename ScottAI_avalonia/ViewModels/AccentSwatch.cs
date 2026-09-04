using CommunityToolkit.Mvvm.ComponentModel;

namespace ScottAI.Avalonia.ViewModels;

public partial class AccentSwatch : ObservableObject
{
    public string Hex { get; }

    [ObservableProperty]
    private bool _isSelected;

    public AccentSwatch(string hex)
    {
        Hex = hex;
    }
}
