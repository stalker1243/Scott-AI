namespace ScottAI.Avalonia.Models;

public enum ToastKind
{
    Success,
    Error,
    Info,
}

public class ToastMessage
{
    public required string Id { get; init; }
    public required string Text { get; init; }
    public required ToastKind Kind { get; init; }
}
