#pragma once

#include <cerrno>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include "dk64vr_math.h"

namespace mk64vrdiag {

struct HeadOffset {
    bool requested = false;
    bool enabled = false;
    unsigned lastGameFrame = 0;
    dk64vr::Vec3 metres;
};

// Process-only QA input: reject the entire offset when any supplied component
// is malformed. No settings registry or saved configuration consumes this data.
inline HeadOffset parseHeadOffset(const char* autostart, const char* x, const char* y, const char* z) {
    HeadOffset result;
    result.requested = x || y || z;
    if (!autostart || !*autostart || std::isspace(static_cast<unsigned char>(*autostart)) || (!x && !y && !z)) return result;
    char* end = nullptr;
    errno = 0;
    const long seconds = std::strtol(autostart, &end, 10);
    if (errno || *end || seconds <= 0 || seconds > 120) return result;
    float values[3] = {};
    const char* inputs[] = {x, y, z};
    for (int i = 0; i < 3; ++i) {
        if (!inputs[i]) continue;
        if (!*inputs[i] || std::isspace(static_cast<unsigned char>(*inputs[i]))) return result;
        errno = 0;
        values[i] = std::strtof(inputs[i], &end);
        if (errno || *end || !std::isfinite(values[i]) || std::fabs(values[i]) > 20.0f) return result;
    }
    result.enabled = true;
    result.lastGameFrame = static_cast<unsigned>(seconds) * 30u;
    result.metres = {values[0], values[1], values[2]};
    return result;
}

inline dk64vr::Pose offsetHead(dk64vr::Pose head, const HeadOffset& offset, bool forceRender, bool synthetic, unsigned gameFrame) {
    if (offset.enabled && forceRender && synthetic && gameFrame > 0 && gameFrame <= offset.lastGameFrame) {
        head.p.x += offset.metres.x;
        head.p.y += offset.metres.y;
        head.p.z += offset.metres.z;
    }
    return head;
}

} // namespace mk64vrdiag
