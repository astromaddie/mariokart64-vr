#include "mk64_interaction.h"
#include <algorithm>
#include <cmath>
namespace mk64vr {
static Vec3 sub(Vec3 a, Vec3 b) { return {a.x-b.x,a.y-b.y,a.z-b.z}; }
static Vec3 add(Vec3 a, Vec3 b) { return {a.x+b.x,a.y+b.y,a.z+b.z}; }
static Vec3 scale(Vec3 a, float s) { return {a.x*s,a.y*s,a.z*s}; }
static float length(Vec3 a) { return float(std::sqrt(double(dot(a,a)))); }
FirstPersonOutput FirstPersonControls::update(const HandSample hands[2], bool active, bool reset,
    bool available, bool held, const FirstPersonConfig& c) {
    FirstPersonOutput out;
    int releaseHand=-1;
    if (!held && !available) holder = -1;
    for (int h=0; h<2; ++h) {
        const auto& hand=hands[h];
        if (!active || reset || !hand.valid) {
            armed[h]=false; previous[h]=hand.grip; wheel[h]=false;
            continue;
        }
        const bool wasArmed=armed[h];
        if (!hand.grip) armed[h]=true;
        const Vec3 d=sub(hand.pose.p,c.wheel);
        const float angle=float(std::atan2(double(d.y),double(d.x)));
        const bool rim=std::abs(length({d.x,d.y,0})-c.radius)<=c.rimTolerance && std::abs(d.z)<=c.rimTolerance;
        if (hand.grip && !previous[h] && armed[h]) {
            if (holder==h && held) { /* rearm retained item after safety reset */ }
            else if (rim && holder!=h) {
                wheel[h]=true; latchAngle[h]=angle; latchWheel[h]=wheelAngle;
            } else if (holder<0 && available && !held) {
                holder=h; out.command=1; available=false;
            } else if (held && holder<0) holder=h;
        }
        if (!hand.grip && previous[h] && wasArmed && holder==h && held) {
            out.command=2; releaseHand=h; out.rear=hand.pose.p.z>c.shoulderZ;
            if (hand.velocityValid && length(hand.velocity)>c.quietSpeed) out.velocity=hand.velocity;
            holder=-1;
        }
        if (!hand.grip) wheel[h]=false;
        previous[h]=hand.grip;
    }
    float angleSum=0; int count=0;
    for (int h=0; h<2; ++h) if(wheel[h]) {
        const Vec3 d=sub(hands[h].pose.p,c.wheel);
        const float a=float(std::atan2(double(d.y),double(d.x)));
        // Clockwise viewed from the seat steers right.
        angleSum+=latchWheel[h]-wrapAngle(a-latchAngle[h]); ++count; out.wheelHands|=1<<h;
    }
    if(count) wheelAngle=std::clamp(angleSum/count,-c.maxTurn,c.maxTurn);
    else wheelAngle=0;
    out.angle=wheelAngle; out.steering=count>0; out.steer=wheelAngle/c.maxTurn; out.itemHand=releaseHand>=0?releaseHand:holder;
    return out;
}
Pose seatPose(Vec3 p, float heading, float height, float forward) {
    Pose seat{quatFromYaw(heading),p};
    seat.p=add(p,quatRotate(seat.q,{0,height,-forward})); return seat;
}
ArmSolution solveArm(Vec3 shoulder, Vec3 wrist, float upperLength, float lowerLength, Vec3 pole, Quat wristRotation) {
    ArmSolution out;
    Vec3 delta=sub(wrist,shoulder); float distance=length(delta);
    Vec3 axis=distance>.0001f?scale(delta,1/distance):Vec3{0,0,-1};
    const float reach=std::clamp(distance,std::abs(upperLength-lowerLength)+.001f,upperLength+lowerLength-.001f);
    out.wrist=add(shoulder,scale(axis,reach));
    Vec3 bend=sub(pole,scale(axis,dot(pole,axis)));
    if(length(bend)<.001f) bend=cross(axis,{0,1,0});
    if(length(bend)<.001f) bend=cross(axis,{1,0,0});
    bend=normalize(bend);
    const float along=(upperLength*upperLength-lowerLength*lowerLength+reach*reach)/(2*reach);
    out.elbow=add(shoulder,add(scale(axis,along),scale(bend,float(std::sqrt(double(std::max(0.f,upperLength*upperLength-along*along)))))));
    const Vec3 z=normalize(sub(out.elbow,shoulder)), x=normalize(cross(bend,z)), y=cross(z,x);
    out.upper=poseMatrix({quatFromBasis(x,y,z),shoulder});
    // Forearm mesh includes the hand: retain the tracked wrist roll/orientation.
    out.lower=poseMatrix({quatNormalize(wristRotation),out.elbow});
    return out;
}
static Quat fromTo(Vec3 from, Vec3 to) {
    from=normalize(from); to=normalize(to); const float d=dot(from,to);
    if(d<-.9999f) { Vec3 axis=normalize(cross(from,{0,1,0})); if(length(axis)<.1f) axis={1,0,0}; return {axis.x,axis.y,axis.z,0}; }
    Vec3 axis=cross(from,to); return quatNormalize({axis.x,axis.y,axis.z,1+d});
}
static Mat4 around(Quat rotation, Vec3 sourcePivot, Vec3 targetPivot, float scaleFactor) {
    Mat4 m=poseMatrix({rotation,{}},1);
    for(int r=0;r<3;r++) for(int c=0;c<3;c++) m.m[r][c]*=scaleFactor;
    const Vec3 p=transformDir(sourcePivot,m);
    m.m[3][0]=targetPivot.x-p.x; m.m[3][1]=targetPivot.y-p.y; m.m[3][2]=targetPivot.z-p.z;
    return m;
}
Mat4 armSkinMatrix(int character, int hand, int lower, int weight, const Pose& wrist, float modelScale, float eyeHeight) {
    const auto& rig=mk64_arm_rigs[character]; const float side=hand==0?1.f:-1.f;
    // Amped model +X is left and +Z forward, opposite the seat X/Z axes.
    Vec3 sourceShoulder{rig.shoulder[0]*side,rig.shoulder[1],rig.shoulder[2]};
    Vec3 sourceElbow{rig.elbow[0]*side,rig.elbow[1],rig.elbow[2]};
    Vec3 sourceWrist{rig.wrist[0]*side,rig.wrist[1],rig.wrist[2]};
    auto toSeat=[&](Vec3 a){return Vec3{-a.x*modelScale,a.y*modelScale,-a.z*modelScale};};
    Vec3 shoulder=toSeat(add({rig.base[0],rig.base[1],rig.base[2]},sourceShoulder)); shoulder.y-=eyeHeight;
    const float upperLength=length(sourceElbow)*modelScale, lowerLength=length(sourceWrist)*modelScale;
    auto solved=solveArm(shoulder,wrist.p,upperLength,lowerLength,{hand?1.f:-1.f,-.5f,.4f},wrist.q);
    const Quat rest=quatFromYaw(3.141592653589793f);
    const Quat upperQ=quatMul(fromTo(toSeat(sourceElbow),sub(solved.elbow,shoulder)),rest);
    const Quat lowerQ=quatMul(fromTo(toSeat(sourceWrist),sub(solved.wrist,solved.elbow)),rest);
    // Grip-pose basis is also camera right/up/back. Rest model basis faces +Z.
    const Quat handQ=quatMul(wrist.q,rest);
    Mat4 upper=around(upperQ,{},shoulder,modelScale);
    Mat4 fore=around(lowerQ,lower?Vec3{}:sourceElbow,solved.elbow,modelScale);
    Mat4 distal=around(handQ,lower?sourceWrist:add(sourceElbow,sourceWrist),solved.wrist,modelScale);
    float t=weight/31.f; Mat4 a=fore,b=distal;
    if(!lower && character!=3) return upper;
    if(!lower) { if(t<.5f) {a=upper;b=fore;t*=2;} else t=(t-.5f)*2; }
    Mat4 out; for(int r=0;r<4;r++)for(int c=0;c<4;c++) out.m[r][c]=a.m[r][c]*(1-t)+b.m[r][c]*t;
    return out;
}

Mat4 kartRegistration(const Mat4& source,const Mat4& seatView,float eyeHeight,float forward) {
    // Remove only native yaw/translation; retain authored tilt, animation and scale.
    const float yaw=float(std::atan2(double(source.m[2][0]),double(source.m[2][2])));
    Mat4 basis=poseMatrix({quatFromYaw(yaw),{source.m[3][0],source.m[3][1],source.m[3][2]}});
    Mat4 target=poseMatrix({quatFromYaw(3.141592653589793f),{0,-eyeHeight,forward}});
    return mul(rigidInverse(basis),mul(target,rigidInverse(seatView)));
}

}
