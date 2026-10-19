"""Export pinned upstream into a new reports directory and add observation hooks."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
COMMIT = 'd1be6fde11ac6e0407606b4e42fe72d34add8037'

HELPER = r'''
// ScottAI diagnostic copy. Experimental changes are explicitly opt-in.
#include "../examples/json.hpp"
#include <set>
using ScottTraceJson = nlohmann::json;
extern "C" void scott_whisper_trace_enable(whisper_context * ctx, bool enabled) {
    ctx->scott_trace_enabled = enabled;
}
extern "C" void scott_whisper_renormalize_enable(whisper_context * ctx, bool enabled) {
    ctx->scott_renormalize_timestamps = enabled;
}
extern "C" void scott_whisper_finish_eot_enable(whisper_context * ctx, bool enabled) {
    ctx->scott_finish_at_eot = enabled;
}
extern "C" void scott_whisper_rank_eot_enable(whisper_context * ctx, bool enabled) {
    ctx->scott_rank_eot = enabled;
}
extern "C" void scott_whisper_dedup_first_enable(whisper_context * ctx, bool enabled) {
    ctx->scott_deduplicate_first_step = enabled;
}
extern "C" void scott_whisper_topk_enable(whisper_context * ctx, bool enabled) {
    ctx->scott_deterministic_topk = enabled;
}
extern "C" void scott_whisper_pool_enable(whisper_context * ctx, bool enabled) {
    ctx->scott_finished_pool = enabled;
}
extern "C" void scott_whisper_pool_limit(whisper_context * ctx, int limit) {
    ctx->scott_pool_sample_limit = limit;
}
extern "C" size_t scott_whisper_token_size(whisper_context * ctx, int id) {
    return ctx->vocab.id_to_token.at(id).size();
}
// Offline probe: copy the encoder's first window, without exposing state ownership.
extern "C" bool scott_whisper_copy_mel(whisper_context * ctx, float * output,
                                      int bands, int frames) {
    const auto & mel = ctx->state->mel;
    if (!output || bands != mel.n_mel || frames <= 0 || frames > 3000 || frames > mel.n_len)
        return false;
    for (int band = 0; band < bands; ++band)
        std::copy_n(mel.data.data() + band * mel.n_len, frames, output + band * frames);
    return true;
}
static void scott_trace_emit(const ScottTraceJson & event) {
    // The pinned logger formats >1024 bytes twice with the same va_list.
    // Call its sink directly so observation never enters that Linux-unsafe path.
    const auto line = std::string("SCOTT_TRACE ") + event.dump() + "\n";
    g_state.log_callback(GGML_LOG_LEVEL_INFO, line.c_str(), g_state.log_callback_user_data);
}
static void scott_trace_snapshot(whisper_context * ctx, whisper_state * state,
        const char * kind, int n_decoders, float temperature, int seek, int seek_end,
        int step, int selected, bool full) {
    if (!ctx->scott_trace_enabled) return;
    try {
        auto decoders = ScottTraceJson::array();
        for (int j = 0; j < n_decoders; ++j) {
            const auto & decoder = state->decoders[j];
            const auto & seq = decoder.sequence;
            double probability_mass = 0;
            for (float probability : decoder.probs) probability_mass += probability;
            auto ids = ScottTraceJson::array();
            auto logprobs = ScottTraceJson::array();
            const size_t first = full || seq.tokens.empty() ? 0 : seq.tokens.size() - 1;
            for (size_t k = first; k < seq.tokens.size(); ++k) {
                ids.push_back(seq.tokens[k].id);
                logprobs.push_back(seq.tokens[k].plog);
            }
            decoders.push_back({{"index", j}, {"failed", decoder.failed},
                {"completed", decoder.completed}, {"has_ts", decoder.has_ts},
                {"seek_delta", decoder.seek_delta}, {"result_len", seq.result_len},
                {"token_count", seq.tokens.size()}, {"sum_logprobs_all", seq.sum_logprobs_all},
                {"sum_logprobs", seq.sum_logprobs}, {"avg_logprobs", seq.avg_logprobs},
                {"score", seq.score}, {"entropy", seq.entropy},
                {"ids", ids}, {"token_logprobs", logprobs}, {"probability_mass", probability_mass}});
        }
        scott_trace_emit({{"kind", kind}, {"temperature", temperature}, {"seek", seek},
            {"seek_end", seek_end}, {"step", step}, {"selected", selected},
            {"no_speech_prob", state->no_speech_prob}, {"full_sequences", full},
            {"decoders", decoders}});
    } catch (...) { scott_trace_emit({{"kind", "trace_error"}}); }
}
'''


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'reports') or output.exists():
        parser.error('Choose a new directory inside reports')
    upstream = ROOT / 'reports/whisper-cpp/upstream'
    actual = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != COMMIT or subprocess.check_output(['git', '-C', str(upstream), 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Pinned source must be unchanged')
    original_sha = sha(upstream / 'src/whisper.cpp')
    previous = json.loads((ROOT / 'reports/whisper-quality/provenance.json').read_text(encoding='utf-8'))
    assert original_sha == next(x['sha256'] for x in previous['cpp_sources'] if x['path'] == 'src/whisper.cpp')
    output.mkdir(parents=True)
    archive = output / 'upstream.zip'
    subprocess.run(['git', '-C', str(upstream), 'archive', '--format=zip', '-o', str(archive), COMMIT], check=True)
    source = output / 'source'
    source.mkdir()
    with zipfile.ZipFile(archive) as zipped:
        assert all((source / x.filename).resolve().is_relative_to(source) for x in zipped.infolist())
        zipped.extractall(source)
    path = source / 'src/whisper.cpp'
    assert sha(path) == original_sha
    before = path.read_text(encoding='utf-8')
    value = before
    def replace(old, new):
        nonlocal value
        assert value.count(old) == 1, old[:100]
        value = value.replace(old, new)
    replace('struct whisper_context {\n', 'struct whisper_context {\n#ifdef SCOTT_DECODER_TRACE\n    bool scott_trace_enabled = false;\n    bool scott_renormalize_timestamps = false;\n    bool scott_finish_at_eot = false;\n    bool scott_rank_eot = false;\n    bool scott_deduplicate_first_step = false;\n    bool scott_deterministic_topk = false;\n    bool scott_finished_pool = false;\n    bool scott_pool_active = false;\n    int scott_pool_sample_limit = 220;\n#endif\n')
    replace('static whisper_global g_state;\n', 'static whisper_global g_state;\n#ifdef SCOTT_DECODER_TRACE\n#include "scott_trace.h"\n#endif\n')
    marker = '            for (int i = 0, n_max = whisper_n_text_ctx(ctx)/2 - 4; i < n_max; ++i) {'
    replace(marker, '''#ifdef SCOTT_DECODER_TRACE
            if (ctx->scott_trace_enabled) scott_trace_emit({{"kind", "prompt"},
                {"seek", seek}, {"seek_end", seek_end}, {"temperature", t_cur},
                {"prompt", prompt}, {"n_decoders", n_decoders_cur},
                {"eot", whisper_token_eot(ctx)}, {"timestamp_begin", whisper_token_beg(ctx)},
                {"sample_limit", whisper_n_text_ctx(ctx)/2 - 4}});
#endif
''' + marker)
    replace(marker, '''            for (int i = 0, n_max =
#ifdef SCOTT_DECODER_TRACE
                (ctx->scott_pool_active ? std::min(whisper_n_text_ctx(ctx)/2 - 4, ctx->scott_pool_sample_limit) : whisper_n_text_ctx(ctx)/2 - 4)
#else
                whisper_n_text_ctx(ctx)/2 - 4
#endif
                ; i < n_max; ++i) {''')
    marker = '                           (has_ts && seek + seek_delta + delta_min >= seek_end)       // end of audio reached (100ms)'
    marker_topk = '        const auto id = dist(decoder.rng);'
    replace(marker_topk, '''#ifdef SCOTT_DECODER_TRACE
        const auto id = (ctx.scott_deterministic_topk || ctx.scott_pool_active) ? logits_id[i].second : dist(decoder.rng);
#else
''' + marker_topk + '\n#endif')
    dedup = ' && i > 0) {'
    assert value.count(dedup) == 1
    replace(dedup, ''' &&
#ifdef SCOTT_DECODER_TRACE
                            (i > 0 || ctx->scott_deduplicate_first_step)
#else
                            i > 0
#endif
                            ) {''')
    marker_first = '                    uint32_t cur_c = 0;'
    replace(marker_first, marker_first + '''
#ifdef SCOTT_DECODER_TRACE
                    std::set<whisper_token> scott_first_step_ids;
#endif''')
    marker_first = '                        auto & cur = beam_candidates[cur_c++];'
    replace(marker_first, '''#ifdef SCOTT_DECODER_TRACE
                        // Equal scores sort by parent index, so duplicate token
                        // IDs need not be adjacent. Filter against every prior pick.
                        if (ctx->scott_deduplicate_first_step && i == 0) {
                            while (cur_c < beam_candidates.size() && scott_first_step_ids.count(
                                beam_candidates[cur_c].sequence.tokens.back().id)) ++cur_c;
                            if (cur_c >= beam_candidates.size()) { decoder.failed = true; continue; }
                            scott_first_step_ids.insert(beam_candidates[cur_c].sequence.tokens.back().id);
                        }
#endif
''' + marker_first)
    replace(marker, '''#ifdef SCOTT_DECODER_TRACE
                           (!ctx->scott_finish_at_eot && !ctx->scott_pool_active && has_ts && seek + seek_delta + delta_min >= seek_end)
#else
''' + marker + '\n#endif')
    marker = '                            if (result_len == 0 && !params.no_timestamps) {'
    replace(marker, '''#ifdef SCOTT_DECODER_TRACE
                            // Offline comparison: retain the sampled prefix before EOT.
                            if (ctx->scott_finish_at_eot && token.id == whisper_token_eot(ctx) &&
                                !params.single_segment && !params.no_timestamps && i > 0) result_len = i;
                            if (ctx->scott_trace_enabled) scott_trace_emit({{"kind", "termination"},
                                {"decoder", j}, {"step", i}, {"seek", seek}, {"seek_end", seek_end},
                                {"temperature", t_cur}, {"result_len", result_len}, {"terminal_id", token.id},
                                {"reason", token.id == whisper_token_eot(ctx) ? "eot" :
                                    (params.max_tokens > 0 && i >= params.max_tokens ? "token_limit" : "audio_end")}});
#endif
''' + marker)
    # Only zero-temperature beam is changed. Stochastic fallback remains pinned
    # upstream and is deliberately reported as a separate, unresolved difference.
    marker = '            n_decoders_cur = std::max(1, n_decoders_cur);'
    replace(marker, marker + '''
#ifdef SCOTT_DECODER_TRACE
            ctx->scott_pool_active = ctx->scott_finished_pool && t_cur < 1e-6f &&
                params.strategy == WHISPER_SAMPLING_BEAM_SEARCH;
            std::vector<beam_candidate> scott_finished;
            std::vector<bool> scott_sampled_eot;
            std::vector<float> scott_eot_logprobs;
            std::set<std::vector<whisper_token>> scott_finished_ids;
            auto scott_ids = [](const beam_candidate & candidate) {
                std::vector<whisper_token> ids;
                for (const auto & token : candidate.sequence.tokens) ids.push_back(token.id);
                return ids;
            };
            auto scott_store = [&](beam_candidate candidate, bool sampled_eot) {
                if (scott_finished.size() >= size_t(n_decoders_cur)) return;
                auto ids = scott_ids(candidate);
                // Deduplicate the final text tokens, including synthetic EOT.
                if (!sampled_eot) ids.push_back(whisper_token_eot(ctx));
                if (!scott_finished_ids.insert(ids).second) return;
                scott_sampled_eot.push_back(sampled_eot);
                scott_eot_logprobs.push_back(sampled_eot ? candidate.sequence.tokens.back().plog : 0.0f);
                if (sampled_eot) candidate.sequence.tokens.pop_back();
                candidate.sequence.result_len = candidate.sequence.tokens.size();
                scott_finished.push_back(std::move(candidate));
            };
#endif''')
    marker = 'const auto tokens_new = whisper_sample_token_topk(*ctx, decoder, params.beam_search.beam_size);'
    replace(marker, '''const auto tokens_new = whisper_sample_token_topk(*ctx, decoder,
#ifdef SCOTT_DECODER_TRACE
                                            params.beam_search.beam_size + (ctx->scott_pool_active ? 1 : 0)
#else
                                            params.beam_search.beam_size
#endif
                                        );''')
    marker = '                    uint32_t cur_c = 0;'
    replace(marker, '''#ifdef SCOTT_DECODER_TRACE
                    if (ctx->scott_pool_active) {
                        std::set<std::vector<whisper_token>> seen;
                        std::vector<beam_candidate> active;
                        // Same bounded selection order as Python: collect EOT
                        // until five non-EOT paths have been retained.
                        for (const auto & candidate : beam_candidates) {
                            if (!seen.insert(scott_ids(candidate)).second) continue;
                            if (candidate.sequence.tokens.back().id == whisper_token_eot(ctx)) {
                                scott_store(candidate, true);
                            } else {
                                active.push_back(candidate);
                                if (active.size() == size_t(n_decoders_cur)) break;
                            }
                        }
                        if (ctx->scott_trace_enabled) scott_trace_emit({{"kind", "pool_select"},
                            {"step", i}, {"seek", seek}, {"temperature", t_cur},
                            {"active_count", active.size()}, {"finished_count", scott_finished.size()},
                            {"beam_size", n_decoders_cur}, {"topk", params.beam_search.beam_size + 1}});
                        if (scott_finished.size() == size_t(n_decoders_cur) || active.empty()) break;
                        beam_candidates = std::move(active);
                        for (int j = 0; j < n_decoders_cur; ++j) {
                            state->decoders[j].completed = false;
                            state->decoders[j].failed = j >= int(beam_candidates.size());
                        }
                    }
#endif
''' + marker)
    marker = '            // rank the resulting sequences and select the best one'
    # Keep the legacy ranking code in its own else block. The pool is bounded to
    # beam_size; finalization takes remaining active prefixes without EOS score.
    replace(marker, '''#ifdef SCOTT_DECODER_TRACE
            if (ctx->scott_pool_active) {
                std::vector<beam_candidate> remaining;
                for (int j = 0; j < n_decoders_cur; ++j) {
                    const auto & decoder = state->decoders[j];
                    if (!decoder.sequence.tokens.empty()) remaining.push_back({j,
                        decoder.seek_delta, decoder.has_ts, decoder.sequence, decoder.grammar});
                }
                std::stable_sort(remaining.begin(), remaining.end(), [](const beam_candidate & a, const beam_candidate & b) {
                    return a.sequence.sum_logprobs_all > b.sequence.sum_logprobs_all;
                });
                for (const auto & candidate : remaining) scott_store(candidate, false);
                double best_score = -INFINITY;
                int selected = -1;
                auto candidates = ScottTraceJson::array();
                for (int j = 0; j < int(scott_finished.size()); ++j) {
                    auto & candidate = scott_finished[j];
                    auto & seq = candidate.sequence;
                    whisper_sequence_score(params, seq);
                    double penalty = std::max(1, seq.result_len);
                    if (params.length_penalty > 0.0f) penalty = pow((5.0 + penalty)/6.0, params.length_penalty);
                    seq.score = seq.sum_logprobs_all / penalty;
                    seq.avg_logprobs = seq.sum_logprobs_all / (seq.result_len + 1);
                    const bool failed = seq.result_len > 32 && seq.entropy < params.entropy_thold;
                    if (!failed && best_score < seq.score) { best_score = seq.score; selected = j; }
                    if (ctx->scott_trace_enabled) candidates.push_back({{"ids", scott_ids(candidate)},
                        {"result_len", seq.result_len}, {"sum_logprobs_all", seq.sum_logprobs_all},
                        {"score", seq.score}, {"avg_logprobs", seq.avg_logprobs}, {"failed", failed},
                        {"sampled_eot", bool(scott_sampled_eot[j])}, {"eot_logprob", scott_eot_logprobs[j]},
                        {"seek_delta", candidate.seek_delta}});
                }
                best_decoder_id = 0;
                auto & decoder = state->decoders[0];
                decoder.failed = selected < 0;
                if (selected >= 0) {
                    const auto & candidate = scott_finished[selected];
                    decoder.sequence = candidate.sequence;
                    decoder.seek_delta = candidate.seek_delta;
                    decoder.has_ts = candidate.has_ts;
                    decoder.grammar = candidate.grammar;
                    decoder.completed = true;
                }
                if (ctx->scott_trace_enabled) scott_trace_emit({{"kind", "pool_rank"},
                    {"seek", seek}, {"temperature", t_cur}, {"selected", selected}, {"candidates", candidates}});
                scott_trace_snapshot(ctx, state, "post_rank", n_decoders_cur, t_cur, seek, seek_end, -1, best_decoder_id, true);
            } else {
#endif
''' + marker)
    replace('            bool success = true;', '''#ifdef SCOTT_DECODER_TRACE
            }
#endif
            bool success = true;''')
    marker = '                    decoder.sequence.tokens.resize(decoder.sequence.result_len);'
    replace(marker, '''#ifdef SCOTT_DECODER_TRACE
                    // Save a genuinely sampled trailing EOT before upstream truncation.
                    double scott_eot_logprob = 0;
                    if (ctx->scott_rank_eot && !decoder.sequence.tokens.empty() &&
                        decoder.sequence.tokens.back().id == whisper_token_eot(ctx) &&
                        decoder.sequence.result_len > 0 &&
                        decoder.sequence.tokens.size() == size_t(decoder.sequence.result_len + 1))
                        scott_eot_logprob = decoder.sequence.tokens.back().plog;
#endif
''' + marker)
    marker = '                    whisper_sequence_score(params, decoder.sequence);'
    replace(marker, marker + '''
#ifdef SCOTT_DECODER_TRACE
                    // Rank only: leave avg_logprobs/fallback/entropy unchanged.
                    if (ctx->scott_rank_eot && decoder.sequence.result_len > 0) {
                        double penalty = decoder.sequence.result_len;
                        if (params.length_penalty > 0.0f) penalty = pow((5.0 + penalty)/6.0, params.length_penalty);
                        decoder.sequence.score += scott_eot_logprob / penalty;
                    }
#endif''')
    marker = '    // compute probs\n    whisper_compute_probs(logits, n_logits, logprobs, probs);'
    replace(marker, '''#ifdef SCOTT_DECODER_TRACE
    // Optional comparison only: Python computes log_softmax after all masks.
    if (ctx.scott_renormalize_timestamps) whisper_compute_logprobs(logits, n_logits, logprobs);
#endif
''' + marker)
    marker = '                // check if all decoders have finished (i.e. completed or failed)'
    replace(marker, '''#ifdef SCOTT_DECODER_TRACE
                scott_trace_snapshot(ctx, state, "step", n_decoders_cur, t_cur, seek, seek_end, i, -1, false);
#endif
''' + marker)
    marker = '            // rank the resulting sequences and select the best one'
    replace(marker, '''#ifdef SCOTT_DECODER_TRACE
            scott_trace_snapshot(ctx, state, "pre_rank", n_decoders_cur, t_cur, seek, seek_end, -1, -1, true);
#endif
''' + marker)
    marker = '                WHISPER_LOG_DEBUG("%s: best decoder = %d\\n", __func__, best_decoder_id);'
    replace(marker, '''#ifdef SCOTT_DECODER_TRACE
                scott_trace_snapshot(ctx, state, "post_rank", n_decoders_cur, t_cur, seek, seek_end, -1, best_decoder_id, true);
#endif
''' + marker)
    path.write_text(value, encoding='utf-8')
    (source / 'src/scott_trace.h').write_text(HELPER, encoding='utf-8')
    (output / 'instrumentation.patch').write_text(''.join(difflib.unified_diff(
        before.splitlines(keepends=True), value.splitlines(keepends=True),
        fromfile='pinned/src/whisper.cpp', tofile='diagnostic/src/whisper.cpp')), encoding='utf-8')
    (output / 'provenance.json').write_text(json.dumps(dict(commit=COMMIT,
        original_sha256=original_sha, instrumented_sha256=sha(path),
        helper_sha256=sha(source / 'src/scott_trace.h'), archive_sha256=sha(archive),
        original_unchanged=sha(upstream / 'src/whisper.cpp') == original_sha,
        baseline_decoder_changes=False, optional_experiments=['renormalize_timestamps', 'finish_at_eot', 'rank_eot', 'deduplicate_first_step', 'deterministic_topk', 'finished_pool', 'pool_sample_limit']), indent=2), encoding='utf-8')
    print(json.dumps(dict(source=str(source), hooks=5)))


if __name__ == '__main__':
    main()
