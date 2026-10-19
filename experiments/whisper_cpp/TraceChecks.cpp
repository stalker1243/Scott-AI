#include "TraceRecorder.h"
#include <stdexcept>
#include <iostream>

int main() {
    int checks = 0;
    auto check = [&](bool condition) {
        if (!condition) throw std::runtime_error("trace_contract_failed");
        ++checks;
    };
    TraceRecorder recorder;
    recorder.begin(true);
    for (size_t i = 0; i < TraceRecorder::max_events + 1; ++i)
        TraceRecorder::log(GGML_LOG_LEVEL_INFO, "SCOTT_TRACE {\"kind\":\"step\"}\n", &recorder);
    auto result = recorder.finish(nullptr);
    check(result.at("events").size() == TraceRecorder::max_events);
    check(result.at("omitted") == 1 && result.at("complete") == false);
    recorder.begin(true);
    const std::string large = "SCOTT_TRACE {\"payload\":\"" + std::string(TraceRecorder::max_bytes, 'x') + "\"}\n";
    TraceRecorder::log(GGML_LOG_LEVEL_INFO, large.c_str(), &recorder);
    result = recorder.finish(nullptr);
    check(result.at("events").empty() && result.at("omitted") == 1);
    recorder.begin(true);
    TraceRecorder::log(GGML_LOG_LEVEL_INFO, "SCOTT_TRACE {broken}\n", &recorder);
    result = recorder.finish(nullptr);
    check(result.at("parse_error") == true && result.at("complete") == false);
    recorder.begin(true);
    TraceRecorder::log(GGML_LOG_LEVEL_INFO, "SCOTT_TRACE {\"kind\":\"step\"}\n", &recorder);
    result = recorder.finish(nullptr);
    check(result.at("complete") == true && result.at("events").size() == 1);
    check(TraceRecorder::hex("\0\xd0", 2) == "00d0");
    check(TraceRecorder::hex("\xd0\xa1", 2) == "d0a1");
    recorder.begin(false);
    TraceRecorder::log(GGML_LOG_LEVEL_INFO, "SCOTT_TRACE {\"kind\":\"step\"}\n", &recorder);
    check(recorder.finish(nullptr).at("events").empty());
    std::cout << "{\"passed\":" << checks << "}" << std::endl;
}
