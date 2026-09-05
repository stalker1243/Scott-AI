namespace ScottAI.Avalonia.Services;

/// <summary>
/// Куда человек может написать, если что-то не работает.
///
/// Здесь только адреса страниц — никаких токенов. Отправлять отчёт из
/// программы напрямую (через API бота) означало бы зашить в неё ключ доступа,
/// а его вытащит любой, кто откроет файл: чужой бот получил бы возможность
/// писать и читать от имени владельца. Поэтому программа лишь открывает чат,
/// а файл человек прикладывает сам — заодно видит, что именно отправляет.
/// </summary>
public static class SupportLinks
{
    /// <summary>Страница создания обращения с заполненным описанием.</summary>
    public const string GitHubIssues = "https://github.com/stalker1243/Scott-AI/issues/new";

    /// <summary>
    /// Чат поддержки в Telegram. Пустая строка прячет кнопку: лучше её не
    /// показывать вовсе, чем вести человека по нерабочему адресу.
    /// </summary>
    public const string Telegram = "";

    public static bool HasTelegram => !string.IsNullOrWhiteSpace(Telegram);
}
