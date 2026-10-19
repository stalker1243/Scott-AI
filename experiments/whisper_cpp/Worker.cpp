// Standalone benchmark. It never opens an audio device or executes recognized text.
#include "whisper.h"
#include "json.hpp"
#include "OwnerWatch.h"
#include "TraceRecorder.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <shellapi.h>
#endif

using Json = nlohmann::json;
using Clock = std::chrono::steady_clock;
namespace fs = std::filesystem;

static double seconds(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now() - start).count();
}
static bool expired(void * opaque) {
    return Clock::now() >= *static_cast<Clock::time_point *>(opaque);
}
static bool begin_encoder(whisper_context *, whisper_state *, void * opaque) {
    return !expired(opaque);
}
static void emit(const Json & value) { std::cout << value.dump() << std::endl; }

// Drain an oversized request without allocating an unbounded std::string.
static bool read_line(std::string & line, bool & too_long) {
    line.clear();
    too_long = false;
    char value;
    while (std::cin.get(value)) {
        if (value == '\n') return true;
        if (line.size() < 65536) line.push_back(value);
        else too_long = true;
    }
    return !line.empty() || too_long;
}

static std::vector<float> read_pcm(const fs::path & root, const std::string & name) {
    const fs::path relative = fs::u8path(name);
    if (relative.empty() || relative.is_absolute() || relative.has_root_path())
        throw std::runtime_error("invalid_pcm_path");
    const auto path = fs::canonical(root / relative);
    const auto within = path.lexically_relative(root);
    if (within.empty() || *within.begin() == ".." || path.extension() != ".f32")
        throw std::runtime_error("invalid_pcm_path");
    const auto size = fs::file_size(path);
    if (!size || size % sizeof(float) || size > 16000 * 60 * sizeof(float))
        throw std::runtime_error("invalid_pcm_size");
    std::vector<float> pcm(size / sizeof(float));
    std::ifstream file(path, std::ios::binary);
    if (!file.read(reinterpret_cast<char *>(pcm.data()), size))
        throw std::runtime_error("pcm_read_failed");
    for (const auto sample : pcm)
        if (!std::isfinite(sample) || std::abs(sample) > 1.0f)
            throw std::runtime_error("invalid_pcm_value");
    return pcm;
}

static int run_worker(int argc, char ** argv) {
    // Optional final JSON selects decoder experiments; defaults preserve the first trial.
    // model, PCM root, backend(cpu/gpu), threads, prompt UTF-8 file, fallback increment, [options].
    if (argc != 7 && argc != 8) return 2;
    try {
        const auto root = fs::canonical(fs::u8path(argv[2]));
        const std::string backend = argv[3];
        if (backend != "cpu" && backend != "gpu") return 2;
        const int threads = std::stoi(argv[4]);
        if (threads < 1 || threads > 64) return 2;
        std::ifstream prompt_file(fs::u8path(argv[5]), std::ios::binary);
        if (!prompt_file) return 2;
        std::string prompt((std::istreambuf_iterator<char>(prompt_file)), {});
        if (prompt.size() > 8192) return 2;
        const float fallback = std::stof(argv[6]);
        if (fallback != 0.0f && fallback != 0.2f) return 2;
        Json options = {{"prompt_space", false}, {"flash_attn", true}, {"no_timestamps", false},
                        {"beam_size", 5}};
        std::uint32_t expected_owner = 0;
        bool trace_requested = false;
        bool renormalize_requested = false;
        bool finish_eot_requested = false;
        bool rank_eot_requested = false;
        bool dedup_first_requested = false;
        bool topk_requested = false;
        bool pool_requested = false;
        int pool_sample_limit = 220;
        bool pool_limit_requested = false;
        std::vector<whisper_token> supplied_prompt_tokens;
        if (argc == 8) {
            if (std::char_traits<char>::length(argv[7]) > 4096) return 2;
            const auto requested = Json::parse(argv[7]);
            if (!requested.is_object()) return 2;
            for (const auto & item : requested.items()) {
                if (item.key() == "pool_sample_limit") {
#ifndef SCOTT_DECODER_TRACE
                    return 2;
#else
                    if (!item.value().is_number_integer()) return 2;
                    const auto value = item.value().get<std::int64_t>();
                    if (value < 1 || value > 220) return 2;
                    pool_sample_limit = static_cast<int>(value);
                    pool_limit_requested = true;
                    continue;
#endif
                }
                if (item.key() == "finish_at_eot" || item.key() == "rank_eot" || item.key() == "deduplicate_first_step" || item.key() == "deterministic_topk" || item.key() == "finished_pool") {
                    if (!item.value().is_boolean()) return 2;
                    const bool value = item.value().get<bool>();
#ifndef SCOTT_DECODER_TRACE
                    if (value) return 2;
#endif
                    if (item.key() == "finish_at_eot") finish_eot_requested = value;
                    else if (item.key() == "rank_eot") rank_eot_requested = value;
                    else if (item.key() == "deduplicate_first_step") dedup_first_requested = value;
                    else if (item.key() == "deterministic_topk") topk_requested = value;
                    else pool_requested = value;
                    continue;
                }
                if (item.key() == "prompt_token_ids") {
#ifndef SCOTT_DECODER_TRACE
                    // This comparison mode is absent from the ordinary worker.
                    return 2;
#else
                    const auto & ids = item.value();
                    if (!ids.is_array() || ids.empty() || ids.size() > 220) return 2;
                    for (const auto & id : ids) {
                        if (!id.is_number_integer()) return 2;
                        const auto value = id.get<std::int64_t>();
                        // Only ordinary multilingual text tokens, never control tokens.
                        if (value < 0 || value >= 50257) return 2;
                        supplied_prompt_tokens.push_back(static_cast<whisper_token>(value));
                    }
                    continue;
#endif
                }
                if (item.key() == "renormalize_timestamps") {
                    if (!item.value().is_boolean()) return 2;
                    renormalize_requested = item.value().get<bool>();
#ifndef SCOTT_DECODER_TRACE
                    if (renormalize_requested) return 2;
#endif
                    continue;
                }
                if (item.key() == "trace_tokens") {
                    if (!item.value().is_boolean()) return 2;
                    trace_requested = item.value().get<bool>();
#ifndef SCOTT_DECODER_TRACE
                    if (trace_requested) return 2;
#endif
                    continue;
                }
                if (item.key() == "owner_pid") {
                    if (!item.value().is_number_integer()) return 2;
                    const auto value = item.value().get<std::int64_t>();
                    if (value < 1 || value > 2147483647) return 2;
                    expected_owner = static_cast<std::uint32_t>(value);
                    continue;
                }
                if (item.key() == "beam_size") {
                    if (!item.value().is_number_integer()) return 2;
                    const auto value = item.value().get<std::int64_t>();
                    // The pinned upstream build has WHISPER_MAX_DECODERS == 8.
                    if (value < 1 || value > 8) return 2;
                    options[item.key()] = value;
                    continue;
                }
                if (!options.contains(item.key()) || !item.value().is_boolean()) return 2;
                options[item.key()] = item.value();
            }
        }
        if (!supplied_prompt_tokens.empty() && options.at("prompt_space").get<bool>()) return 2;
        if (pool_requested && (finish_eot_requested || rank_eot_requested || dedup_first_requested || topk_requested)) return 2;
        if (pool_limit_requested && !pool_requested) return 2;
        OwnerWatch owner(expected_owner);
#ifdef SCOTT_DECODER_TRACE
        TraceRecorder recorder;
        whisper_log_set(TraceRecorder::log, &recorder);
#endif
        if (options.at("prompt_space").get<bool>() && !prompt.empty() && prompt.front() != ' ')
            prompt.insert(prompt.begin(), ' ');
        auto context_params = whisper_context_default_params();
        context_params.use_gpu = backend == "gpu";
        context_params.flash_attn = options.at("flash_attn").get<bool>();
        const auto start = Clock::now();
        // MinGW's upstream narrow-file loader loses Unicode model paths. Stream
        // the same weights through filesystem's native path without a RAM copy.
        std::ifstream model_file(fs::u8path(argv[1]), std::ios::binary);
        if (!model_file) { emit({{"event", "error"}, {"error", "model_load_failed"}}); return 3; }
        whisper_model_loader loader = {};
        loader.context = &model_file;
        loader.read = [](void * opaque, void * output, size_t size) -> size_t {
            auto & stream = *static_cast<std::ifstream *>(opaque);
            stream.read(static_cast<char *>(output), size);
            return static_cast<size_t>(stream.gcount());
        };
        loader.eof = [](void * opaque) { return static_cast<std::ifstream *>(opaque)->eof(); };
        loader.close = [](void * opaque) { static_cast<std::ifstream *>(opaque)->close(); };
        std::unique_ptr<whisper_context, decltype(&whisper_free)> context(
            whisper_init_with_params(&loader, context_params), whisper_free);
        if (!context) { emit({{"event", "error"}, {"error", "model_load_failed"}}); return 3; }
        for (auto token : supplied_prompt_tokens)
            if (token >= whisper_token_eot(context.get())) return 2;
        Json ready = {{"event", "ready"}, {"protocol", 1}, {"version", whisper_version()},
              {"requested_backend", backend}, {"load_seconds", seconds(start)},
              {"threads", threads}, {"temperature_increment", fallback},
              {"decoder_options", options},
              {"owner_monitor", {{"pid", owner.pid()}, {"mode", owner.mode()}}},
              {"system_info", whisper_print_system_info()}};
#ifdef SCOTT_DECODER_TRACE
        ready["decoder_trace"] = {{"supported", true}, {"enabled", trace_requested},
            {"protocol", 1}, {"max_events", TraceRecorder::max_events},
            {"max_event_bytes", TraceRecorder::max_bytes}, {"max_vocabulary_bytes", TraceRecorder::max_vocabulary_bytes}};
        ready["renormalize_timestamps"] = renormalize_requested;
        ready["candidate_completion"] = {{"finish_at_eot", finish_eot_requested}, {"rank_eot", rank_eot_requested}};
        ready["deduplicate_first_step"] = dedup_first_requested;
        ready["deterministic_topk"] = topk_requested;
        ready["finished_pool"] = {{"enabled", pool_requested}, {"temperature", "zero_only"},
            {"capacity", options.at("beam_size")}, {"topk", options.at("beam_size").get<int>() + 1},
            {"fallback", "upstream_unchanged"}, {"entropy_filter", "upstream_unchanged"},
            {"sample_limit", pool_sample_limit}};
        ready["prompt_tokens"] = {{"source", supplied_prompt_tokens.empty() ? "native_tokenizer" : "provided"},
            {"ids", supplied_prompt_tokens}, {"max_tokens", 220}};
        scott_whisper_trace_enable(context.get(), trace_requested);
        scott_whisper_renormalize_enable(context.get(), renormalize_requested);
        scott_whisper_finish_eot_enable(context.get(), finish_eot_requested);
        scott_whisper_rank_eot_enable(context.get(), rank_eot_requested);
        scott_whisper_dedup_first_enable(context.get(), dedup_first_requested);
        scott_whisper_topk_enable(context.get(), topk_requested);
        scott_whisper_pool_enable(context.get(), pool_requested);
        scott_whisper_pool_limit(context.get(), pool_sample_limit);
#endif
        emit(ready);

        std::string line;
        bool too_long;
        while (read_line(line, too_long)) {
            Json id = nullptr;
            try {
                if (too_long) throw std::runtime_error("request_too_large");
                const auto request = Json::parse(line);
                id = request.at("id");
                if (!id.is_number_integer()) throw std::runtime_error("invalid_id");
                if (request.value("op", "transcribe") == "quit") break;
                if (request.value("op", "transcribe") != "transcribe")
                    throw std::runtime_error("invalid_op");
                const auto pcm = read_pcm(root, request.at("pcm").get<std::string>());
                const int timeout_ms = request.value("timeout_ms", 120000);
                if (timeout_ms < 1 || timeout_ms > 120000)
                    throw std::runtime_error("invalid_timeout");
                auto deadline = Clock::now() + std::chrono::milliseconds(timeout_ms);
                auto params = whisper_full_default_params(WHISPER_SAMPLING_BEAM_SEARCH);
                params.n_threads = threads;
                params.language = "ru";
                params.no_context = true;
                params.no_timestamps = options.at("no_timestamps").get<bool>();
                params.initial_prompt = prompt.c_str();
                if (!supplied_prompt_tokens.empty()) {
                    params.initial_prompt = nullptr;
                    params.prompt_tokens = supplied_prompt_tokens.data();
                    params.prompt_n_tokens = static_cast<int>(supplied_prompt_tokens.size());
                }
                params.print_progress = false;
                params.print_realtime = false;
                params.print_timestamps = false;
                params.suppress_nst = true;
                params.temperature = 0.0f;
                params.temperature_inc = fallback;
                params.beam_search.beam_size = options.at("beam_size").get<int>();
                params.greedy.best_of = 5;
                params.abort_callback = expired;
                params.abort_callback_user_data = &deadline;
                params.encoder_begin_callback = begin_encoder;
                params.encoder_begin_callback_user_data = &deadline;
                const auto decode_start = Clock::now();
#ifdef SCOTT_DECODER_TRACE
                recorder.begin(trace_requested);
#endif
                const int code = whisper_full(context.get(), params, pcm.data(), pcm.size());
                const auto elapsed = seconds(decode_start);
                if (Clock::now() >= deadline) {
                    emit({{"event", "result"}, {"id", id}, {"error", "timeout"}, {"seconds", elapsed}});
                    continue;
                }
                if (code != 0) throw std::runtime_error("decode_failed");
                std::string text;
                Json segments = Json::array();
                for (int segment = 0; segment < whisper_full_n_segments(context.get()); ++segment) {
                    text += whisper_full_get_segment_text(context.get(), segment);
                    double log_sum = 0;
                    int count = 0;
                    for (int token = 0; token < whisper_full_n_tokens(context.get(), segment); ++token) {
                        const auto data = whisper_full_get_token_data(context.get(), segment, token);
                        if (data.id < whisper_token_eot(context.get()) && std::isfinite(data.plog)) {
                            log_sum += data.plog;
                            ++count;
                        }
                    }
                    segments.push_back({{"no_speech_prob", whisper_full_get_segment_no_speech_prob(context.get(), segment)},
                        {"mean_text_token_logprob", count ? Json(log_sum / count) : Json(nullptr)}});
                }
                Json result = {{"event", "result"}, {"id", id}, {"text", text},
                      {"seconds", elapsed}, {"segments", segments}};
#ifdef SCOTT_DECODER_TRACE
                if (trace_requested) result["decoder_trace"] = recorder.finish(context.get());
#endif
                emit(result);
            } catch (const std::exception &) {
                // Input paths/content stay in the caller's report, never in error diagnostics.
                emit({{"event", "result"}, {"id", id}, {"error", "invalid_request_or_decode"}});
            }
        }
        return 0;
    } catch (const std::exception &) {
        emit({{"event", "error"}, {"error", "initialization_failed"}});
        return 3;
    }
}

int main(int argc, char ** argv) {
#ifdef _WIN32
    try {
        // Use the original UTF-16 command line; the CRT ANSI argv can replace
        // Cyrillic, Chinese and emoji before filesystem ever sees them.
        std::unique_ptr<wchar_t *, decltype(&LocalFree)> wide(
            CommandLineToArgvW(GetCommandLineW(), &argc), LocalFree);
        if (!wide) throw std::runtime_error("arguments_failed");
        std::vector<std::string> utf8;
        utf8.reserve(argc);
        for (int i = 0; i < argc; ++i) {
            const auto value = wide.get()[i];
            const int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value, -1,
                nullptr, 0, nullptr, nullptr);
            if (size <= 0) throw std::runtime_error("arguments_failed");
            std::string converted(size, '\0');
            if (WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value, -1,
                    converted.data(), size, nullptr, nullptr) != size)
                throw std::runtime_error("arguments_failed");
            converted.pop_back();
            utf8.push_back(std::move(converted));
        }
        std::vector<char *> pointers;
        for (auto & value : utf8) pointers.push_back(value.data());
        pointers.push_back(nullptr);
        return run_worker(argc, pointers.data());
    } catch (const std::exception &) {
        emit({{"event", "error"}, {"error", "initialization_failed"}});
        return 3;
    }
#else
    return run_worker(argc, argv);
#endif
}
