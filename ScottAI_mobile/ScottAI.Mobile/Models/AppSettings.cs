namespace ScottAI.Mobile.Models;

/// <summary>
/// Всё, что приложение помнит между запусками.
///
/// Здесь же лежит ключ привязки — единственное, что даёт телефону право
/// командовать компьютером. Он выдаётся один раз, при привязке, и узнать его
/// повторно нельзя: на компьютере он не показывается даже в списке устройств.
/// Поэтому потеря этого файла означает привязку заново, а не восстановление.
/// </summary>
public class AppSettings
{
    /// <summary>Адрес компьютера в домашней сети — например, 192.168.1.5:8000.</summary>
    public string Host { get; set; } = "";

    /// <summary>Ключ устройства. Уходит в заголовке каждой команды.</summary>
    public string Token { get; set; } = "";

    /// <summary>Как компьютер назвал это устройство при привязке.</summary>
    public string DeviceName { get; set; } = "";

    /// <summary>Акцентный цвет — тот же набор, что в лаунчере на компьютере.</summary>
    public string Accent { get; set; } = "#3B82F6";

    /// <summary>Тёмная тема по умолчанию: приложением пользуются вечером чаще.</summary>
    public string Theme { get; set; } = "dark";

    /// <summary>Размер текста в чате. Телефон держат дальше от глаз, чем монитор.</summary>
    public double FontScale { get; set; } = 1.0;

    public bool Paired => Token.Length > 0 && Host.Length > 0;
}
