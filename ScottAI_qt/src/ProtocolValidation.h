#pragma once
#include <QJsonArray>
#include <QJsonObject>
#include <QSet>
#include <cmath>

inline bool protocolDraftValid(const QJsonObject &data) {
    const auto name = data.value("name").toString().trimmed();
    if (name.isEmpty() || name.size() > 100 || !data.value("description").isString() || data.value("description").toString().size() > 2000 ||
        !data.value("schedule").isString() || !data.value("enabled").isBool() || !data.value("stop_on_error").isBool()) return false;
    const auto repeat = data.value("repeat_count").toDouble();
    if (repeat < 1 || repeat > 20 || std::floor(repeat) != repeat) return false;
    const auto steps = data.value("steps").toArray();
    if (steps.isEmpty() || steps.size() > 40) return false;
    bool active = false;
    for (const auto &value : steps) {
        const auto step = value.toObject(); const auto pause = step.value("pause").toDouble(-1);
        if (!step.value("text").isString() || step.value("text").toString().trimmed().isEmpty() || step.value("text").toString().size() > 2000 ||
            !step.value("enabled").isBool() || pause < 0 || pause > 60 || !std::isfinite(pause)) return false;
        active |= step.value("enabled").toBool();
    }
    if (!active || !data.value("phrases").isArray() || data.value("phrases").toArray().size() > 20) return false;
    for (const auto &phrase : data.value("phrases").toArray())
        if (!phrase.isString() || phrase.toString().trimmed().isEmpty() || phrase.toString().size() > 200) return false;
    return true;
}
inline QJsonObject protocolDraft(const QJsonObject &record) {
    QJsonObject draft;
    for (const auto &key : {"name", "description", "steps", "phrases", "enabled", "repeat_count", "stop_on_error"}) draft[key] = record[key];
    draft["schedule"] = record.value("schedule").isString() ? record["schedule"] : record.value("schedule_text").toString();
    if (!draft.value("repeat_count").isDouble()) draft["repeat_count"] = 1;
    if (!draft.value("stop_on_error").isBool()) draft["stop_on_error"] = true;
    auto steps = draft.value("steps").toArray();
    for (int i = 0; i < steps.size(); ++i) { auto step = steps[i].toObject(); if (!step.value("enabled").isBool()) step["enabled"] = true; steps[i] = step; }
    draft["steps"] = steps;
    return draft;
}
inline bool protocolRecordValid(const QJsonObject &data) {
    const auto runs = data.value("runs").toDouble(-1);
    return !data.value("id").toString().isEmpty() && data.value("created").isString() && data.value("schedule_text").isString() &&
           (data.value("last_run").isNull() || data.value("last_run").isString()) && runs >= 0 && std::floor(runs) == runs && protocolDraftValid(protocolDraft(data));
}
inline bool protocolJobValid(const QJsonObject &data) {
    if (data.isEmpty()) return true;
    const QSet<QString> states{"running", "cancelling", "completed", "failed", "cancelled"};
    const auto total = data.value("total").toDouble(-1), current = data.value("current").toDouble(-1);
    if (data.value("id").toString().isEmpty() || data.value("protocol_id").toString().isEmpty() || !data.value("name").isString() ||
        !states.contains(data.value("state").toString()) || !data.value("message").isString() || !data.value("error").isString() ||
        !data.value("steps").isArray() || total < 1 || total > 800 || current < 0 || current > total || std::floor(total) != total || std::floor(current) != current) return false;
    for (const auto &value : data.value("steps").toArray()) {
        const auto step = value.toObject();
        if (!step.value("text").isString() || !step.value("ok").isBool() || !step.value("response").isString()) return false;
    }
    return data.value("steps").toArray().size() <= total;
}
