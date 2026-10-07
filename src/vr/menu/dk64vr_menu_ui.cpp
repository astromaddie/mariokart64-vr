// MK64 keeps the author's stock frontend. A custom VR settings UI is not approved.
// Persistent vr.toml and MK64_VR_* overrides provide initial configuration.
#include "dk64vr_menu_ui.h"
namespace dk64vr::menu {
void uiCreate() {}
bool uiReady() { return false; }
bool uiOpen(const dk64vr_settings_t&, const Facts&, double, uint32_t) { return false; }
void uiClose() {}
void uiRefreshSettings(const dk64vr_settings_t&) {}
bool uiIsOpen() { return false; }
void uiFrame(const FrameIn&, const Facts&) {}
FrameOut uiTake() { return {}; }
void uiAct(const std::string&) {}
void uiLocate(const std::string&) {}
}
