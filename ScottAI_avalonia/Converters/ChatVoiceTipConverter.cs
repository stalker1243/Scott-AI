using System;
using System.Globalization;
using Avalonia.Data.Converters;

namespace ScottAI.Avalonia.Converters;

/// <summary>
/// Почему кнопка озвучки в чате недоступна.
///
/// Недоступная кнопка без объяснения выглядит поломкой — а причина здесь
/// внешняя и находится в другом месте программы.
/// </summary>
public class ChatVoiceTipConverter : IValueConverter
{
    public static readonly ChatVoiceTipConverter Instance = new();

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
        => value is true
            ? "Scott сейчас молчит совсем — переключатель в шапке или в настройках звука"
            : "Зачитывать ли вслух ответы в этой переписке";

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture)
        => throw new NotSupportedException();
}
