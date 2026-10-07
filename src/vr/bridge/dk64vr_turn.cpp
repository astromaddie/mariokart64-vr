#include "dk64vr_turn.h"
#include "dk64vr_math.h"
#include <algorithm>
#include <cmath>

namespace dk64vr {
void ComfortTurn::reset() { *this = ComfortTurn(); }

int ComfortTurn::apply(float degrees, double now, bool applicable) {
    if (!applicable || !headingValid) return 0;
    if (!active) {
        target = heading + shownDelta;
        releaseFrom = 0;
    }
    target -= degrees * 0.01745329252f;
    active = true;
    start = now;
    remainder += degrees;
    const int whole = int(remainder);
    remainder -= float(whole);
    return whole;
}

TurnEnd ComfortTurn::update(float gameHeading, double now, bool applicable, bool overtaken) {
    heading = headingValid ? heading + wrapAngle(gameHeading - raw) : gameHeading;
    raw = gameHeading;
    headingValid = true;
    if (!applicable) {
        const bool hadTurn = active || releaseFrom != 0;
        active = false;
        shownDelta = releaseFrom = remainder = 0;
        return hadTurn ? TurnEnd::NotApplicable : TurnEnd::None;
    }
    if (active) {
        const float delta = target - heading;
        shownDelta = delta;
        // A new smooth increment can be smaller than the arrival tolerance. Keep its
        // fractional request until a later frame, so a slow hold still drives the game.
        const bool settled = now > start && std::fabs(delta) < 0.004f;
        const bool timedOut = now - start > 8.0;
        if (settled || timedOut || overtaken) {
            active = false;
            // The view is periodic. Abandoning unwrapped debt must not unwind whole extra
            // revolutions: the equivalent shortest angle starts at the same physical view.
            releaseFrom = settled ? 0 : wrapAngle(delta);
            release = now;
            shownDelta = releaseFrom;
            remainder = 0;
            return settled ? TurnEnd::Arrived : (timedOut ? TurnEnd::TimedOut : TurnEnd::Overtaken);
        }
    }
    else if (releaseFrom != 0) {
        const float t = float(std::clamp((now - release) / 0.4, 0.0, 1.0));
        shownDelta = releaseFrom * (1 - t * t * (3 - 2 * t));
        if (t >= 1) shownDelta = releaseFrom = 0;
    }
    else shownDelta = 0;
    return TurnEnd::None;
}
}
