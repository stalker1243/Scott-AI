#pragma once
#include "whisper.h"
#include "json.hpp"
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <mutex>
#include <string>

#ifdef SCOTT_DECODER_TRACE
extern "C" void scott_whisper_trace_enable(whisper_context *, bool);
extern "C" size_t scott_whisper_token_size(whisper_context *, int);
extern "C" void scott_whisper_renormalize_enable(whisper_context *, bool);
extern "C" void scott_whisper_finish_eot_enable(whisper_context *, bool);
extern "C" void scott_whisper_rank_eot_enable(whisper_context *, bool);
extern "C" void scott_whisper_dedup_first_enable(whisper_context *, bool);
extern "C" void scott_whisper_topk_enable(whisper_context *, bool);
extern "C" void scott_whisper_pool_enable(whisper_context *, bool);
extern "C" void scott_whisper_pool_limit(whisper_context *, int);

// Only a diagnostic build has hooks. Raw byte pieces remain lossless hex because
// a single tokenizer piece may end in the middle of a UTF-8 character.
class TraceRecorder {
    using Json = nlohmann::json;
    std::mutex mutex;
    Json events = Json::array();
    size_t bytes = 0;
    size_t omitted = 0;
    bool active = false;
    std::atomic<bool> parse_error{false};
public:
    static constexpr size_t max_events = 512;
    static constexpr size_t max_bytes = 1024 * 1024;
    static constexpr size_t max_vocabulary_bytes = 64 * 1024;
    ~TraceRecorder() { whisper_log_set(nullptr, nullptr); }
    void begin(bool enabled) {
        std::lock_guard<std::mutex> lock(mutex);
        events = Json::array();
        bytes = omitted = 0;
        parse_error = false;
        active = enabled;
    }
    static void log(ggml_log_level, const char * line, void * opaque) noexcept {
        if (!line) return;
        auto & self = *static_cast<TraceRecorder *>(opaque);
        const std::string prefix = "SCOTT_TRACE ";
        try {
            if (std::char_traits<char>::compare(line, prefix.c_str(), std::min(prefix.size(), std::char_traits<char>::length(line))) == 0
                    && std::char_traits<char>::length(line) >= prefix.size()) {
                std::lock_guard<std::mutex> lock(self.mutex);
                if (!self.active) return;
                const size_t length = std::char_traits<char>::length(line);
                if (self.events.size() >= max_events || length > max_bytes - self.bytes) {
                    ++self.omitted;
                    return;
                }
                self.events.push_back(Json::parse(line + prefix.size()));
                self.bytes += length;
                return;
            }
        } catch (...) { self.parse_error = true; return; }
        std::fputs(line, stderr);
    }
    static std::string hex(const char * piece, size_t size) {
        static const char alphabet[] = "0123456789abcdef";
        std::string result;
        if (piece) for (size_t i = 0; i < size; ++i) {
            const auto value = static_cast<unsigned char>(piece[i]);
            result.push_back(alphabet[value >> 4]);
            result.push_back(alphabet[value & 15]);
        }
        return result;
    }
    Json finish(whisper_context * ctx) {
        std::lock_guard<std::mutex> lock(mutex);
        active = false;
        Json vocabulary = Json::object();
        size_t vocabulary_bytes = 2;
        size_t vocabulary_omitted = 0;
        auto add = [&](const Json & ids) {
            for (const auto & item : ids) {
                const int id = item.get<int>();
                const auto key = std::to_string(id);
                if (vocabulary.contains(key)) continue;
                const auto encoded = hex(whisper_token_to_str(ctx, id), scott_whisper_token_size(ctx, id));
                const auto size = key.size() + encoded.size() + 8;
                if (size > max_vocabulary_bytes - vocabulary_bytes) { ++vocabulary_omitted; continue; }
                vocabulary[key] = encoded;
                vocabulary_bytes += size;
            }
        };
        for (const auto & event : events) {
            if (event.contains("prompt")) add(event.at("prompt"));
            if (event.contains("decoders")) for (const auto & decoder : event.at("decoders"))
                if (decoder.contains("ids")) add(decoder.at("ids"));
            if (event.contains("candidates")) for (const auto & candidate : event.at("candidates"))
                if (candidate.contains("ids")) add(candidate.at("ids"));
        }
        return {{"protocol", 1}, {"events", events}, {"vocabulary_hex", vocabulary},
                {"omitted", omitted}, {"parse_error", parse_error.load()},
                {"vocabulary_omitted", vocabulary_omitted},
                {"complete", omitted == 0 && vocabulary_omitted == 0 && !parse_error.load()},
                {"max_events", max_events}, {"max_event_bytes", max_bytes},
                {"max_vocabulary_bytes", max_vocabulary_bytes}};
    }
};
#endif
