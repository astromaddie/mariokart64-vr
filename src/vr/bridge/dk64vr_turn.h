#pragma once

namespace dk64vr {

// Pure state behind the game's whole-degree import, with a 300 ms stale-request limit.
struct TurnRequests {
    int degrees = 0;
    double at = 0;
    void add(int step, double now) { degrees += step; at = now; }
    int take(bool applicable, double now) {
        const int step = degrees;
        degrees = 0;
        return applicable && now - at <= 0.3 ? step : 0;
    }
};

enum class TurnEnd { None, Arrived, TimedOut, Overtaken, NotApplicable };

// Display-heading compensation. Game headings wrap; requested/display headings do not.
// Camera cuts/recentre call reset. Rejection is immediate; abandoned turns unwind by the
// equivalent shortest angle in 0.4 s, without replaying extra revolutions of unwrapped debt.
struct ComfortTurn {
    bool active = false, headingValid = false;
    float target = 0, heading = 0, raw = 0, shownDelta = 0, releaseFrom = 0, remainder = 0;
    double start = 0, release = 0;
    void reset();
    int apply(float degrees, double now, bool applicable);
    TurnEnd update(float gameHeading, double now, bool applicable, bool overtaken);
};

}
