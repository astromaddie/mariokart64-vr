#pragma once
#include "dk64vr_math.h"
#include "../../../include/mk64_first_person.h"
#include "../../../include/mk64_arm_rig.h"
namespace mk64vr {
using namespace dk64vr;
struct HandSample { bool valid = false, grip = false; Pose pose; Vec3 velocity; bool velocityValid = false; };
struct FirstPersonConfig {
    Vec3 wheel{0, -.28f, -.25f}; float radius = .18f, rimTolerance = .12f;
    float maxTurn = 1.05f, shoulderZ = .12f, quietSpeed = .35f;
};
struct FirstPersonOutput {
    bool steering = false; float steer = 0, angle = 0; int wheelHands = 0;
    int itemHand = -1, command = 0; bool rear = false; Vec3 velocity;
};
// State changes only on trusted grip edges. Invalid tracking never means release.
class FirstPersonControls {
public:
    FirstPersonOutput update(const HandSample hands[2], bool active, bool reset,
        bool itemAvailable, bool itemHeld, const FirstPersonConfig& config);
private:
    bool armed[2]{}, previous[2]{}, wheel[2]{};
    float latchAngle[2]{}, latchWheel[2]{}, wheelAngle = 0;
    int holder = -1;
};
// Cache only trusted seat-local attachment; invalid samples cannot overwrite it.
class HeldItemAttachment {
public:
    void update(bool held, int hand, bool tracked, Vec3 position);
    bool transform(Mat4& model, const Mat4& seatView) const;
private:
    bool valid=false;
    Vec3 local;
};
struct ArmSolution { Vec3 elbow, wrist; Mat4 upper, lower; };
ArmSolution solveArm(Vec3 shoulder, Vec3 wrist, float upperLength, float lowerLength,
    Vec3 pole, Quat wristRotation);
Mat4 kartRegistration(const Mat4& source, const Mat4& seatView, float eyeHeight, float forward);
Mat4 armSkinMatrix(int character, int hand, int lower, int weight, const Pose& wrist, float scale, float eyeHeight);
Pose seatPose(Vec3 racerPosition, float heading, float height, float forward);
}
