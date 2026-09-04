using System.Collections.ObjectModel;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using ScottAI.Avalonia.Models;
using ScottAI.Avalonia.Services;

namespace ScottAI.Avalonia.ViewModels;

public class DailyBar
{
    public string Label { get; init; } = "";
    public int Value { get; init; }
    public double HeightFraction { get; init; }
}

public class DistributionRow
{
    public string Label { get; init; } = "";
    public int Value { get; init; }
    public double PercentFraction { get; init; }
}

public partial class AnalyticsViewModel : ViewModelBase
{
    private readonly BackendClient _client;

    [ObservableProperty] private bool _loading;
    [ObservableProperty] private string? _error;
    [ObservableProperty] private int _totalCommands;
    [ObservableProperty] private double _averageResponseTime;
    [ObservableProperty] private string _trendText = "—";

    public ObservableCollection<DailyBar> DailyBars { get; } = new();
    public ObservableCollection<DistributionRow> CommandTypes { get; } = new();
    public ObservableCollection<DistributionRow> TopApps { get; } = new();
    public ObservableCollection<AnalyticsRecommendation> Recommendations { get; } = new();

    public AnalyticsViewModel(BackendClient client)
    {
        _client = client;
        _ = Refresh();
    }

    [RelayCommand]
    private async Task Refresh()
    {
        Loading = true;
        Error = null;
        try
        {
            var analytics = await _client.GetAnalyticsAsync();
            var trend = await _client.GetAnalyticsTrendAsync();
            var recs = await _client.GetRecommendationsAsync();

            DailyBars.Clear();
            CommandTypes.Clear();
            TopApps.Clear();
            Recommendations.Clear();

            if (analytics is not null)
            {
                TotalCommands = analytics.TotalCommands;
                AverageResponseTime = analytics.ResponseTime?.Average ?? 0;

                if (analytics.Daily is not null)
                {
                    var max = 1;
                    foreach (var c in analytics.Daily.Commands) if (c > max) max = c;
                    for (var i = 0; i < analytics.Daily.Dates.Count; i++)
                    {
                        var value = analytics.Daily.Commands[i];
                        DailyBars.Add(new DailyBar
                        {
                            Label = analytics.Daily.Dates[i].Length >= 5 ? analytics.Daily.Dates[i][5..] : analytics.Daily.Dates[i],
                            Value = value,
                            HeightFraction = System.Math.Max(0.03, (double)value / max),
                        });
                    }
                }

                if (analytics.CommandTypes is not null)
                {
                    for (var i = 0; i < analytics.CommandTypes.Types.Count; i++)
                    {
                        CommandTypes.Add(new DistributionRow
                        {
                            Label = analytics.CommandTypes.Types[i],
                            Value = analytics.CommandTypes.Counts[i],
                            PercentFraction = i < analytics.CommandTypes.Percentages.Count ? analytics.CommandTypes.Percentages[i] / 100.0 : 0,
                        });
                    }
                }

                if (analytics.TopApps is not null)
                {
                    var max = 1;
                    foreach (var c in analytics.TopApps.UsageCount) if (c > max) max = c;
                    for (var i = 0; i < analytics.TopApps.Apps.Count; i++)
                    {
                        TopApps.Add(new DistributionRow
                        {
                            Label = analytics.TopApps.Apps[i],
                            Value = analytics.TopApps.UsageCount[i],
                            PercentFraction = (double)analytics.TopApps.UsageCount[i] / max,
                        });
                    }
                }
            }

            if (trend is not null)
            {
                TrendText = trend.Trend switch
                {
                    "up" => $"+{trend.TrendPercentage:0.#}%",
                    "down" => $"{trend.TrendPercentage:0.#}%",
                    _ => "стабильно",
                };
            }

            foreach (var r in recs) Recommendations.Add(r);
        }
        catch (System.Exception ex)
        {
            Error = ex.Message;
        }
        finally
        {
            Loading = false;
        }
    }
}
