// A bounded, fixed-command bridge to Windows Core Audio. No shell or Qt runtime.
#define NOMINMAX
#include <windows.h>
#include <mmdeviceapi.h>
#include <endpointvolume.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

struct Audio {
    IMMDeviceEnumerator *enumerator = nullptr;
    IMMDevice *device = nullptr;
    IAudioEndpointVolume *volume = nullptr;
    ~Audio() {
        if (volume) volume->Release();
        if (device) device->Release();
        if (enumerator) enumerator->Release();
    }
    bool open() {
        return SUCCEEDED(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                   __uuidof(IMMDeviceEnumerator), reinterpret_cast<void **>(&enumerator)))
            && SUCCEEDED(enumerator->GetDefaultAudioEndpoint(eRender, eMultimedia, &device))
            && SUCCEEDED(device->Activate(__uuidof(IAudioEndpointVolume), CLSCTX_ALL, nullptr,
                   reinterpret_cast<void **>(&volume)));
    }
};

int failure(const char *code) {
    std::printf("{\"protocol\":1,\"success\":false,\"code\":\"%s\"}\n", code);
    return 1;
}
int main(int argc, char **argv) {
    if (argc == 2 && std::strcmp(argv[1], "probe") == 0) {
        std::puts("{\"protocol\":1,\"success\":true}"); return 0;
    }
    const bool status = argc == 2 && std::strcmp(argv[1], "status") == 0;
    const bool set = argc == 3 && std::strcmp(argv[1], "volume") == 0;
    const bool delta = argc == 3 && std::strcmp(argv[1], "delta") == 0;
    const bool mute = argc == 3 && std::strcmp(argv[1], "mute") == 0;
    if (!status && !set && !delta && !mute) return failure("invalid_command");
    double value = 0;
    if (!status) {
        char *end = nullptr;
        value = std::strtod(argv[2], &end);
        if (!end || end == argv[2] || *end || !std::isfinite(value)
            || (set && (value < 0 || value > 100)) || (delta && std::abs(value) > 100)
            || (mute && value != 0 && value != 1)) return failure("invalid_value");
    }
    if (FAILED(CoInitializeEx(nullptr, COINIT_MULTITHREADED))) return failure("initialization");
    int result;
    {
        Audio audio;
        float current = 0;
        BOOL muted = FALSE;
        if (!audio.open()) result = failure("no_output_device");
        else if (FAILED(audio.volume->GetMasterVolumeLevelScalar(&current))) result = failure("read_failed");
        else {
            HRESULT changed = S_OK;
            if (set || delta) changed = audio.volume->SetMasterVolumeLevelScalar(
                static_cast<float>(std::clamp(set ? value / 100 : current + value / 100, 0., 1.)), nullptr);
            else if (mute) changed = audio.volume->SetMute(value == 1, nullptr);
            if (FAILED(changed)) result = failure("write_failed");
            else if (FAILED(audio.volume->GetMasterVolumeLevelScalar(&current)) || FAILED(audio.volume->GetMute(&muted)))
                result = failure("verification_failed");
            else {
                std::printf("{\"protocol\":1,\"success\":true,\"volume\":%d,\"muted\":%s}\n",
                    static_cast<int>(std::lround(current * 100)), muted ? "true" : "false");
                result = 0;
            }
        }
    }
    CoUninitialize();
    return result;
}
