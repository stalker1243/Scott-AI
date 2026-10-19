// Offline diagnostics only. No beam search, audio devices, or command execution.
#include "whisper.h"
#include "json.hpp"
#include "OwnerWatch.h"
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <set>
#include <string>
#include <vector>
#ifdef _WIN32
#include <shellapi.h>
#endif
using Json = nlohmann::json;
namespace fs = std::filesystem;
extern "C" bool scott_whisper_copy_mel(whisper_context *, float *, int, int);
extern "C" size_t scott_whisper_token_size(whisper_context *, int);

static fs::path input_path(const fs::path & root, const std::string & name) {
    const auto relative = fs::u8path(name);
    if (relative.empty() || relative.has_root_path()) throw std::runtime_error("invalid_input_path");
    const auto path = fs::canonical(root / relative);
    const auto within = path.lexically_relative(root);
    if (within.empty() || *within.begin() == ".." || !fs::is_regular_file(path))
        throw std::runtime_error("invalid_input_path");
    return path;
}
static std::vector<float> read_floats(const fs::path & path, size_t min, size_t max, float limit) {
    const auto bytes = fs::file_size(path);
    if (bytes % 4 || bytes / 4 < min || bytes / 4 > max) throw std::runtime_error("invalid_float_size");
    std::vector<float> data(bytes / 4);
    std::ifstream file(path, std::ios::binary);
    if (!file.read(reinterpret_cast<char *>(data.data()), bytes)) throw std::runtime_error("input_read_failed");
    for (auto value : data) if (!std::isfinite(value) || std::abs(value) > limit)
        throw std::runtime_error("invalid_float_value");
    return data;
}
static void write_floats(const fs::path & path, const std::vector<float> & data) {
    // Files are new, fixed names inside this run's newly created directory.
    if (fs::exists(path)) throw std::runtime_error("output_exists");
    std::ofstream file(path, std::ios::binary);
    file.write(reinterpret_cast<const char *>(data.data()), data.size() * sizeof(float));
    if (!file) throw std::runtime_error("output_write_failed");
}
static std::vector<int> token_ids(const Json & values, size_t max) {
    if (!values.is_array() || values.empty() || values.size() > max)
        throw std::runtime_error("invalid_token_count");
    std::vector<int> result;
    for (const auto & value : values) {
        if (!value.is_number_integer() || value.get<int64_t>() < 0 || value.get<int64_t>() >= 51866)
            throw std::runtime_error("invalid_token_id");
        result.push_back(value.get<int>());
    }
    return result;
}
static void validate(const Json & config, const fs::path & root) {
    if (!config.is_object() || config.at("protocol") != 1) throw std::runtime_error("invalid_protocol");
    for (const auto key : {"flash_attn", "full_replay"})
        if (config.contains(key) && !config.at(key).is_boolean()) throw std::runtime_error("invalid_probe_option");
    const auto & cases = config.at("cases");
    if (!cases.is_array() || cases.empty() || cases.size() > 32) throw std::runtime_error("invalid_case_count");
    for (const auto & item : cases) {
        input_path(root, item.at("pcm").get<std::string>());
        input_path(root, item.at("mel").get<std::string>());
        if (item.at("n_mels") != 80 && item.at("n_mels") != 128) throw std::runtime_error("invalid_mel_bands");
        const auto & plans = item.at("plans");
        if (!plans.is_array() || plans.empty() || plans.size() > 8) throw std::runtime_error("invalid_plan_count");
        for (const auto & plan : plans) {
            const auto prefix = token_ids(plan.at("prefix"), 220);
            const auto sequence = token_ids(plan.at("sequence"), 96);
            if (prefix.size() + sequence.size() > 448) throw std::runtime_error("invalid_context_length");
        }
        // Validate data before allocating/loading any model or GPU resources.
        read_floats(input_path(root, item.at("pcm")), 1, 16000 * 60, 1.0f);
        const auto size = item.at("n_mels").get<size_t>() * 3000;
        read_floats(input_path(root, item.at("mel")), size, size, 10.0f);
    }
}
static int run(int argc, char ** argv) {
    if (argc != 6) return 2;
    try {
        const auto config_path = fs::canonical(fs::u8path(argv[2]));
        const auto root = config_path.parent_path();
        if (fs::file_size(config_path) > 2 * 1024 * 1024) throw std::runtime_error("config_too_large");
        std::ifstream config_file(config_path);
        const auto config = Json::parse(config_file);
        validate(config, root);
        const std::string backend = argv[3];
        if (backend != "gpu" && backend != "cpu") throw std::runtime_error("invalid_backend");
        const auto threads = std::stoi(argv[4]);
        if (threads < 1 || threads > 64) throw std::runtime_error("invalid_threads");
        const auto owner_pid = std::stoul(argv[5]);
        if (!owner_pid || owner_pid > 2147483647) throw std::runtime_error("invalid_owner");
        OwnerWatch owner(static_cast<uint32_t>(owner_pid));
        const auto output = root / "cpp-output";
        if (fs::exists(output)) throw std::runtime_error("output_exists");
        auto params = whisper_context_default_params();
        params.use_gpu = backend == "gpu";
        params.flash_attn = config.value("flash_attn", true);
        const bool full_replay = config.value("full_replay", false);
        std::ifstream model(fs::u8path(argv[1]), std::ios::binary);
        if (!model) throw std::runtime_error("model_load_failed");
        whisper_model_loader loader = {};
        loader.context = &model;
        loader.read = [](void * opaque, void * buffer, size_t size) {
            auto & file = *static_cast<std::ifstream *>(opaque);
            file.read(static_cast<char *>(buffer), size);
            return static_cast<size_t>(file.gcount());
        };
        loader.eof = [](void * opaque) { return static_cast<std::ifstream *>(opaque)->eof(); };
        loader.close = [](void * opaque) { static_cast<std::ifstream *>(opaque)->close(); };
        std::unique_ptr<whisper_context, decltype(&whisper_free)> context(
            whisper_init_with_params(&loader, params), whisper_free);
        if (!context) throw std::runtime_error("model_load_failed");
        const int vocab = whisper_n_vocab(context.get());
        for (const auto & item : config.at("cases")) {
            if (item.at("n_mels") != whisper_model_n_mels(context.get())) throw std::runtime_error("model_mel_mismatch");
            for (const auto & plan : item.at("plans"))
                for (const auto key : {"prefix", "sequence"})
                    for (const auto & id : plan.at(key))
                        if (id.get<int>() >= vocab) throw std::runtime_error("model_token_mismatch");
        }
        fs::create_directory(output);
        Json results = {{"protocol", 1}, {"vocab", vocab}, {"backend", backend},
            {"flash_attn", params.flash_attn}, {"full_replay", full_replay},
            {"threads", threads}, {"forced_sequences", true},
            {"eot", whisper_token_eot(context.get())}, {"sot", whisper_token_sot(context.get())},
            {"timestamp_begin", whisper_token_beg(context.get())},
            {"system_info", whisper_print_system_info()}, {"rows", Json::array()}};
        std::set<int> used;
        size_t case_index = 0;
        for (const auto & item : config.at("cases")) {
            const int bands = item.at("n_mels");
            const auto pcm = read_floats(input_path(root, item.at("pcm")), 1, 16000 * 60, 1);
            const auto mel = read_floats(input_path(root, item.at("mel")), bands * 3000, bands * 3000, 10);
            if (whisper_pcm_to_mel(context.get(), pcm.data(), static_cast<int>(pcm.size()), threads))
                throw std::runtime_error("mel_failed");
            std::vector<float> native_mel(bands * 3000);
            if (!scott_whisper_copy_mel(context.get(), native_mel.data(), bands, 3000))
                throw std::runtime_error("mel_copy_failed");
            const auto native_name = std::to_string(case_index) + "-native-mel.f32";
            write_floats(output / native_name, native_mel);
            for (const std::string mode : {"common", "native"}) {
                const auto & input = mode == "common" ? mel : native_mel;
                if (whisper_set_mel(context.get(), input.data(), 3000, bands) || whisper_encode(context.get(), 0, threads))
                    throw std::runtime_error("encode_failed");
                size_t plan_index = 0;
                for (const auto & plan : item.at("plans")) {
                    auto tokens = token_ids(plan.at("prefix"), 220);
                    const auto sequence = token_ids(plan.at("sequence"), 96);
                    used.insert(tokens.begin(), tokens.end()); used.insert(sequence.begin(), sequence.end());
                    std::vector<float> logits;
                    logits.reserve(sequence.size() * vocab);
                    for (size_t step = 0; step < sequence.size(); ++step) {
                        const int count = step ? 1 : static_cast<int>(tokens.size());
                        const int past = step ? static_cast<int>(tokens.size()) - 1 : 0;
                        const int * input_tokens = step ? &tokens.back() : tokens.data();
                        if (whisper_decode(context.get(), input_tokens, count, past, threads))
                            throw std::runtime_error("decode_failed");
                        const auto row = whisper_get_logits(context.get()) + (count - 1) * vocab;
                        for (int i = 0; i < vocab; ++i) if (!std::isfinite(row[i])) throw std::runtime_error("nonfinite_logits");
                        logits.insert(logits.end(), row, row + vocab);
                        tokens.push_back(sequence[step]);
                    }
                    // Full passes run after the incremental sequence, so they
                    // cannot replace its KV state between sampled positions.
                    std::vector<float> full_logits;
                    double all_steps_delta = 0;
                    if (full_replay) {
                        auto prefix = token_ids(plan.at("prefix"), 220);
                        full_logits.reserve(sequence.size() * vocab);
                        for (size_t step = 0; step < sequence.size(); ++step) {
                            if (whisper_decode(context.get(), prefix.data(), static_cast<int>(prefix.size()), 0, threads))
                                throw std::runtime_error("full_replay_failed");
                            const auto row = whisper_get_logits(context.get()) + (prefix.size() - 1) * vocab;
                            for (int k = 0; k < vocab; ++k) {
                                if (!std::isfinite(row[k])) throw std::runtime_error("nonfinite_full_logits");
                                all_steps_delta = std::max(all_steps_delta,
                                    static_cast<double>(std::abs(row[k] - logits[step * vocab + k])));
                            }
                            full_logits.insert(full_logits.end(), row, row + vocab);
                            prefix.push_back(sequence[step]);
                        }
                    }
                    // Preserve the earlier final-step cache comparison too.
                    tokens.pop_back();
                    if (whisper_decode(context.get(), tokens.data(), static_cast<int>(tokens.size()), 0, threads))
                        throw std::runtime_error("replay_failed");
                    const auto replay = whisper_get_logits(context.get()) + (tokens.size() - 1) * vocab;
                    double replay_delta = 0;
                    for (int i = 0; i < vocab; ++i) replay_delta = std::max(replay_delta,
                        static_cast<double>(std::abs(replay[i] - logits[logits.size() - vocab + i])));
                    const auto name = std::to_string(case_index) + "-" + mode + "-" + std::to_string(plan_index++) + ".f32";
                    write_floats(output / name, logits);
                    Json result = {{"id", item.at("id")}, {"mode", mode}, {"plan", plan.at("name")},
                        {"prefix", plan.at("prefix")}, {"sequence", sequence}, {"logits", name},
                        {"incremental_full_max_abs", replay_delta},
                        {"shape", {sequence.size(), vocab}}, {"native_mel", native_name}};
                    if (full_replay) {
                        const auto full_name = name.substr(0, name.size() - 4) + "-full.f32";
                        write_floats(output / full_name, full_logits);
                        result["full_logits"] = full_name;
                        result["incremental_full_all_steps_max_abs"] = all_steps_delta;
                    }
                    results["rows"].push_back(result);
                }
            }
            ++case_index;
            std::cout << Json({{"completed", case_index}}).dump() << std::endl;
        }
        Json dictionary = Json::object();
        const char digits[] = "0123456789abcdef";
        for (const auto id : used) {
            const auto text = whisper_token_to_str(context.get(), id);
            std::string hex;
            for (size_t i = 0; i < scott_whisper_token_size(context.get(), id); ++i) {
                const auto byte = static_cast<unsigned char>(text[i]);
                hex += digits[byte >> 4]; hex += digits[byte & 15];
            }
            dictionary[std::to_string(id)] = hex;
        }
        results["vocabulary_hex"] = dictionary;
        std::ofstream file(output / "result.json"); file << results.dump(2);
        if (!file) throw std::runtime_error("output_write_failed");
        return 0;
    } catch (const std::exception &) {
        // Avoid printing request contents or input paths in failure messages.
        std::cout << Json({{"error", "prefix_probe_failed"}}).dump() << std::endl;
        return 2;
    }
}
#ifdef _WIN32
int main() {
    int argc = 0;
    auto wide = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!wide) return 2;
    std::vector<std::string> args;
    for (int i = 0; i < argc; ++i) {
        const int size = WideCharToMultiByte(CP_UTF8, 0, wide[i], -1, nullptr, 0, nullptr, nullptr);
        std::string value(size, '\0');
        WideCharToMultiByte(CP_UTF8, 0, wide[i], -1, value.data(), size, nullptr, nullptr);
        value.pop_back(); args.push_back(std::move(value));
    }
    LocalFree(wide);
    std::vector<char *> pointers; for (auto & arg : args) pointers.push_back(arg.data());
    return run(argc, pointers.data());
}
#else
int main(int argc, char ** argv) { return run(argc, argv); }
#endif
